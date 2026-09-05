use crate::{
    adapters::{ModelOperation, Services, TelemetryEvent},
    domain,
    event::parse_sns_event,
    policy::{sender_allowed, DeliveryConfig},
};
use serde::Serialize;
use serde_json::Value;
use std::{collections::BTreeMap, env};

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct RuntimeResponse {
    pub status: String,
    pub reason: Option<String>,
    pub delivery_mode: Option<String>,
    pub response: Option<String>,
    pub location_source: Option<String>,
    pub call_counts: BTreeMap<String, usize>,
    pub sms_api_called: bool,
    pub sns_published: bool,
}

impl RuntimeResponse {
    fn ignored(reason: &str) -> Self {
        Self {
            status: "ignored".into(),
            reason: Some(reason.into()),
            delivery_mode: None,
            response: None,
            location_source: None,
            call_counts: BTreeMap::new(),
            sms_api_called: false,
            sns_published: false,
        }
    }
}

fn emit(
    services: &mut Services,
    event: &str,
    status: &str,
    outcome: Option<&str>,
    provider: Option<&str>,
    intent: Option<&str>,
) {
    services.telemetry.emit(TelemetryEvent {
        event: event.into(),
        status: status.into(),
        provider: provider.map(str::to_owned),
        intent: intent.map(str::to_owned),
        outcome: outcome.map(str::to_owned),
        metrics: BTreeMap::new(),
    });
}

fn adapter_call(services: &mut Services, operation: &str, provider: &str) {
    emit(
        services,
        "adapter_call",
        "attempt",
        Some(operation),
        Some(provider),
        None,
    );
}

/// Deterministic orchestration entry point used by the local capture harness and future Lambda wiring.
pub fn handle_event(
    event: &Value,
    config: &DeliveryConfig,
    allowed_phone: Option<&str>,
    services: &mut Services,
) -> RuntimeResponse {
    let Some(message) = parse_sns_event(event) else {
        return RuntimeResponse::ignored("unsupported_event");
    };
    if !sender_allowed(&message, allowed_phone) {
        return RuntimeResponse::ignored("sender_not_allowed");
    }

    // Keep the DynamoDB partition key aligned with the Python oracle: provider formatting is
    // normalized before context reads/writes, while the original destination value is retained
    // for an outbound provider call.
    let normalized_sender = crate::policy::normalized_e164(&message.origination_number);
    let sender = if normalized_sender.is_empty() {
        message.origination_number.clone()
    } else {
        normalized_sender
    };
    adapter_call(services, "context_read", "dynamodb");
    let load = match services.context.load(&sender) {
        Ok(value) => value,
        Err(error) => {
            emit(
                services,
                "context_read",
                "failure",
                Some(&error.category),
                Some("dynamodb"),
                None,
            );
            crate::adapters::ContextLoad {
                history: Vec::new(),
                readable: false,
            }
        }
    };
    let created_at = format!(
        "{}#{}",
        if message.timestamp.is_empty() {
            "missing-timestamp"
        } else {
            &message.timestamp
        },
        if message.message_id.is_empty() {
            "missing-id"
        } else {
            &message.message_id
        }
    );
    adapter_call(services, "context_reserve", "dynamodb");
    match services.context.reserve(
        &sender,
        &message.message_id,
        &created_at,
        &message.message_body,
    ) {
        Ok(true) => {}
        Ok(false) => return RuntimeResponse::ignored("duplicate_delivery"),
        Err(error) => {
            emit(
                services,
                "context_write",
                "failure",
                Some(&error.category),
                Some("dynamodb"),
                None,
            );
            return failed(config, "storage_unavailable", None, None, services);
        }
    }

    let response = if let Some(redirect) = domain::current_status_redirect(&message.message_body) {
        emit(
            services,
            "route",
            "success",
            Some("current_status_redirect"),
            None,
            None,
        );
        redirect.to_owned()
    } else if domain::current_news_question(&message.message_body) {
        emit(
            services,
            "route",
            "success",
            Some("current_news_boundary"),
            None,
            None,
        );
        domain::CURRENT_DATA_LIMITATION_REPLY.to_owned()
    } else {
        adapter_call(services, ModelOperation::Interpret.as_str(), "bedrock");
        let interpretation_text = match services.model.converse(domain::model_request(
            ModelOperation::Interpret,
            &message.message_body,
            &load.history,
            None,
            80,
            0.0,
        )) {
            Ok(value) => value,
            Err(error) => {
                emit(
                    services,
                    "bedrock_failure",
                    "failure",
                    Some(&error.category),
                    Some("bedrock"),
                    None,
                );
                return finish(
                    config,
                    &message,
                    &sender,
                    &created_at,
                    domain::WEATHER_EXTRACTION_FALLBACK,
                    None,
                    services,
                );
            }
        };
        let interpretation = match crate::models::parse_interpretation(&interpretation_text) {
            Ok(value) => value,
            Err(_) => {
                emit(
                    services,
                    "bedrock_failure",
                    "failure",
                    Some("malformed_output"),
                    Some("bedrock"),
                    None,
                );
                return finish(
                    config,
                    &message,
                    &sender,
                    &created_at,
                    domain::WEATHER_EXTRACTION_FALLBACK,
                    None,
                    services,
                );
            }
        };
        let route = domain::route(&message.message_body, interpretation);
        emit(
            services,
            "route",
            "success",
            Some(route.intent()),
            None,
            Some(route.intent()),
        );
        match route {
            domain::Route::General { interpretation } => general(
                &message.message_body,
                &load.history,
                interpretation,
                services,
            ),
            domain::Route::Clarify { .. } => bounded_model(
                services,
                ModelOperation::Clarify,
                &message.message_body,
                &load.history,
                None,
                domain::WEATHER_EXTRACTION_FALLBACK,
            ),
            domain::Route::InformationLookup { .. } => {
                information_lookup(&message.message_body, &load.history, services)
            }
            domain::Route::Weather { interpretation } => weather(
                &message.message_body,
                &load.history,
                load.readable,
                interpretation,
                services,
            ),
            domain::Route::FireStatus { interpretation } => fire_status(
                &message.message_body,
                &load.history,
                interpretation,
                services,
            ),
        }
    };
    finish(
        config,
        &message,
        &sender,
        &created_at,
        &response,
        None,
        services,
    )
}

fn general(
    text: &str,
    history: &[crate::models::ContextInteraction],
    interpretation: crate::models::Interpretation,
    services: &mut Services,
) -> String {
    let _ = interpretation;
    bounded_model(
        services,
        ModelOperation::General,
        text,
        history,
        None,
        domain::FALLBACK_REPLY,
    )
}

fn weather(
    text: &str,
    history: &[crate::models::ContextInteraction],
    context_readable: bool,
    interpretation: crate::models::Interpretation,
    services: &mut Services,
) -> String {
    let explicit = domain::parse_coordinates(text);
    if domain::contains_coordinate_attempt(text) && explicit.is_none() {
        return bounded_model(
            services,
            ModelOperation::CoordinateCorrection,
            text,
            history,
            None,
            domain::WEATHER_COORDINATE_FALLBACK,
        );
    }
    if let Some(model_coordinates) = interpretation.coordinates {
        if explicit.is_none() && interpretation.location_text.is_none() {
            return bounded_model(
                services,
                ModelOperation::CoordinateCorrection,
                text,
                history,
                None,
                domain::WEATHER_COORDINATE_FALLBACK,
            );
        }
        if explicit.is_some() && Some(model_coordinates) != explicit {
            return bounded_model(
                services,
                ModelOperation::CoordinateCorrection,
                text,
                history,
                None,
                domain::WEATHER_COORDINATE_FALLBACK,
            );
        }
    }
    let (coordinates, label) = if let Some(coordinates) = explicit {
        (coordinates, "provided GPS coordinates".into())
    } else {
        let location = interpretation.location_text.clone().unwrap_or_default();
        if location.is_empty() || (interpretation.location_source == "history" && !context_readable)
        {
            return bounded_model(
                services,
                ModelOperation::LocationRequest,
                text,
                history,
                None,
                domain::WEATHER_LOCATION_PROMPT,
            );
        }
        adapter_call(services, "location", "location_provider");
        let resolution = match services.location.resolve(&location) {
            Ok(value) => value,
            Err(_) => {
                return bounded_model(
                    services,
                    ModelOperation::LocationRequest,
                    text,
                    history,
                    None,
                    domain::WEATHER_LOCATION_UNAVAILABLE,
                )
            }
        };
        let Some(candidate) = resolution.candidate else {
            let fallback = match resolution.outcome.as_str() {
                "ambiguous" => domain::WEATHER_LOCATION_AMBIGUOUS,
                "unavailable" => domain::WEATHER_LOCATION_UNAVAILABLE,
                _ => domain::WEATHER_LOCATION_NOT_FOUND,
            };
            return bounded_model(
                services,
                ModelOperation::LocationRequest,
                text,
                history,
                None,
                fallback,
            );
        };
        (candidate.coordinates, candidate.name)
    };
    weather_at(text, history, interpretation, coordinates, label, services)
}

fn weather_at(
    text: &str,
    history: &[crate::models::ContextInteraction],
    interpretation: crate::models::Interpretation,
    coordinates: crate::models::Coordinates,
    label: String,
    services: &mut Services,
) -> String {
    adapter_call(services, "weather", "open_meteo");
    let forecast = match services.weather.forecast(coordinates) {
        Ok(value) => value,
        Err(_) => {
            return bounded_model(
                services,
                ModelOperation::WeatherUnavailable,
                text,
                history,
                None,
                domain::WEATHER_PROVIDER_FALLBACK,
            )
        }
    };
    let Some(selected) = domain::select_weather_period(&forecast, &interpretation.time_window)
    else {
        return domain::WEATHER_PROVIDER_FALLBACK.into();
    };
    let guidance = domain::trip_guidance(&selected, &interpretation.activity);
    let fire = if domain::contains_fire_term(text) {
        adapter_call(services, "fire_ban", "athena");
        services.fire_ban.lookup(coordinates).ok()
    } else {
        None
    };
    let evidence = Some(domain::weather_evidence(
        &label,
        coordinates,
        &selected,
        &guidance,
        fire.as_ref(),
    ));
    let mut advice = bounded_model(
        services,
        ModelOperation::Advice,
        text,
        history,
        evidence,
        domain::WEATHER_ADVICE_FALLBACK,
    );
    if domain::contains_absolute_safety_claim(&advice)
        || domain::contains_stale_history_location(&advice, history, &label)
    {
        advice = domain::deterministic_weather_summary(&selected, &guidance);
    }
    if let Some(fire) = fire {
        let fire_text = domain::fire_ban_sms(&fire);
        let budget = domain::MAX_SMS_CHARS.saturating_sub(domain::septet_count(&fire_text) + 1);
        advice = format!(
            "{} {}",
            fire_text,
            domain::truncate_septets(&advice, budget)
        );
    }
    domain::bound_sms(&advice, domain::WEATHER_ADVICE_FALLBACK)
}

fn fire_status(
    text: &str,
    history: &[crate::models::ContextInteraction],
    interpretation: crate::models::Interpretation,
    services: &mut Services,
) -> String {
    let coordinates = domain::parse_coordinates(text);
    let (coordinates, label) = if let Some(point) = coordinates {
        (point, None)
    } else {
        let location = interpretation.location_text.unwrap_or_default();
        if location.is_empty() {
            return bounded_model(
                services,
                ModelOperation::LocationRequest,
                text,
                history,
                None,
                "Please send GPS coordinates or a named Ontario park.",
            );
        }
        adapter_call(services, "location", "location_provider");
        let resolution = match services.location.resolve(&location) {
            Ok(value) => value,
            Err(_) => {
                return bounded_model(
                    services,
                    ModelOperation::LocationRequest,
                    text,
                    history,
                    None,
                    "I couldn't verify that park. Please send GPS coordinates or a named park.",
                )
            }
        };
        let Some(candidate) = resolution.candidate else {
            return bounded_model(
                services,
                ModelOperation::LocationRequest,
                text,
                history,
                None,
                "I couldn't verify that park. Please send GPS coordinates or a named park.",
            );
        };
        (candidate.coordinates, Some(candidate.name))
    };
    adapter_call(services, "fire_ban", "athena");
    let mut result = match services.fire_ban.lookup(coordinates) {
        Ok(value) => value,
        Err(_) => domain::unknown_fire_result("query_failure"),
    };
    if result.park_name.is_none() {
        result.park_name = label;
    }
    domain::bound_sms(
        &domain::fire_ban_sms(&result),
        "Fire status is unknown; verify Ontario Parks alerts.",
    )
}

fn information_lookup(
    text: &str,
    history: &[crate::models::ContextInteraction],
    services: &mut Services,
) -> String {
    adapter_call(services, "retrieval", "bedrock");
    let results = match services.retriever.retrieve(text) {
        Ok(value) => domain::normalize_retrieval(value),
        Err(_) => return domain::RAG_RETRIEVAL_FAILURE.into(),
    };
    if !domain::usable_retrieval(&results) {
        return domain::RAG_UNUSABLE.into();
    }
    let answer = bounded_model(
        services,
        ModelOperation::RagResponse,
        text,
        history,
        Some(domain::retrieval_evidence(&results)),
        domain::RAG_RESPONSE_FAILURE,
    );
    if !domain::safe_rag_answer(&answer, &results) {
        return domain::RAG_UNUSABLE.into();
    }
    let citation = domain::citation_suffix(&results[0].citation);
    let budget = domain::MAX_SMS_CHARS.saturating_sub(domain::septet_count(&citation) + 1);
    domain::bound_sms(
        &format!("{} {}", domain::truncate_septets(&answer, budget), citation),
        domain::RAG_UNUSABLE,
    )
}

fn bounded_model(
    services: &mut Services,
    operation: ModelOperation,
    text: &str,
    history: &[crate::models::ContextInteraction],
    evidence: Option<String>,
    fallback: &str,
) -> String {
    adapter_call(services, operation.as_str(), "bedrock");
    match services.model.converse(domain::model_request(
        operation, text, history, evidence, 96, 0.0,
    )) {
        Ok(value) => domain::bound_sms(&value, fallback),
        Err(_) => fallback.into(),
    }
}

fn finish(
    config: &DeliveryConfig,
    message: &crate::event::InboundMessage,
    sender: &str,
    _created_at: &str,
    response: &str,
    location_source: Option<&str>,
    services: &mut Services,
) -> RuntimeResponse {
    let response = domain::bound_sms(response, domain::FALLBACK_REPLY);
    if !config.is_capture() {
        adapter_call(services, "sms", "end_user_messaging");
        if services
            .sms
            .send(&message.origination_number, &response)
            .is_err()
        {
            emit(
                services,
                "sms_send_failed",
                "failure",
                Some("sms_send_failed"),
                Some("end_user_messaging"),
                None,
            );
            return failed(
                config,
                "sms_send_failed",
                Some(&response),
                location_source,
                services,
            );
        }
    }
    adapter_call(services, "context_complete", "dynamodb");
    if services
        .context
        .complete(sender, &message.message_id, &response)
        .is_err()
    {
        emit(
            services,
            "context_write",
            "failure",
            Some("storage_unavailable"),
            Some("dynamodb"),
            None,
        );
    }
    let counts = services.telemetry.snapshot();
    RuntimeResponse {
        status: if config.is_capture() {
            "captured".into()
        } else {
            "replied".into()
        },
        reason: None,
        delivery_mode: Some(config.delivery_mode.clone()),
        response: Some(response),
        location_source: location_source.map(str::to_owned),
        call_counts: counts,
        sms_api_called: !config.is_capture(),
        sns_published: false,
    }
}

fn failed(
    config: &DeliveryConfig,
    reason: &str,
    response: Option<&String>,
    location_source: Option<&str>,
    services: &mut Services,
) -> RuntimeResponse {
    RuntimeResponse {
        status: "failed".into(),
        reason: Some(reason.into()),
        delivery_mode: Some(config.delivery_mode.clone()),
        response: response.cloned(),
        location_source: location_source.map(str::to_owned),
        call_counts: services.telemetry.snapshot(),
        sms_api_called: false,
        sns_published: false,
    }
}

pub fn handle_event_from_env(
    event: &Value,
) -> Result<RuntimeResponse, crate::policy::DeliveryConfigError> {
    let Some(message) = parse_sns_event(event) else {
        return Ok(RuntimeResponse::ignored("unsupported_event"));
    };
    let allowed_phone = env::var("ALLOWED_PHONE_NUMBER").ok();
    if !sender_allowed(&message, allowed_phone.as_deref()) {
        return Ok(RuntimeResponse::ignored("sender_not_allowed"));
    }
    let config = DeliveryConfig::from_env()?;
    Ok(RuntimeResponse {
        status: "failed".into(),
        reason: Some("adapters_not_wired".into()),
        delivery_mode: Some(config.delivery_mode),
        response: None,
        location_source: None,
        call_counts: BTreeMap::new(),
        sms_api_called: false,
        sns_published: false,
    })
}
