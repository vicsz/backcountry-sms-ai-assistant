use backcountry_runtime::{
    adapters::ContextLoad,
    fakes::{capture_services, CallLog},
    gsm7::{bound_sms, septet_count},
    handle_event,
    models::parse_interpretation,
    normalized_e164,
    policy::DeliveryConfig,
};
use chrono::{DateTime, FixedOffset};
use serde_json::json;
use std::collections::BTreeMap;

fn sns_event(sender: &str, body: &str) -> serde_json::Value {
    json!({
        "Records": [{"Sns": {
            "MessageId": "synthetic-message-id",
            "Timestamp": "2026-09-05T12:00:00.000Z",
            "Message": serde_json::to_string(&json!({
                "originationNumber": sender,
                "messageBody": body,
                "messageId": "provider-message-id"
            })).unwrap()
        }}]
    })
}

fn capture_config() -> DeliveryConfig {
    DeliveryConfig {
        test_mode: true,
        deployment_environment: "test".into(),
        delivery_mode: "capture".into(),
    }
}

#[test]
fn parses_nested_sns_provider_event_and_rejects_malformed_shapes() {
    let parsed = backcountry_runtime::parse_sns_event(&sns_event("+14165551234", "weather"));
    assert_eq!(parsed.unwrap().message_body, "weather");
    assert!(backcountry_runtime::parse_sns_event(&json!({"Records": []})).is_none());
    assert!(backcountry_runtime::parse_sns_event(
        &json!({"Records": [{"Sns": {"Message": "not-json"}}]})
    )
    .is_none());
}

#[test]
fn sender_guard_and_capture_boundary_are_fail_closed() {
    let event = sns_event("+1 (416) 555-1234", "tell me a joke");
    let log = CallLog::default();
    let mut services = capture_services(
        &log,
        vec![],
        Ok(ContextLoad {
            history: vec![],
            readable: true,
        }),
        Ok(true),
        Err(backcountry_runtime::adapters::AdapterError::new("not_used")),
        Err(backcountry_runtime::adapters::AdapterError::new("not_used")),
        Ok(vec![]),
        Ok(backcountry_runtime::domain::unknown_fire_result("not_used")),
    );
    let ignored = handle_event(
        &event,
        &capture_config(),
        Some("+14165551234"),
        &mut services,
    );
    assert_eq!(ignored.status, "captured");
    assert_eq!(ignored.reason, None);
    assert_eq!(
        ignored.response.as_deref(),
        Some(backcountry_runtime::domain::WEATHER_EXTRACTION_FALLBACK)
    );
    assert!(!ignored.sms_api_called);
    assert!(!ignored.sns_published);

    let mut blocked_services = capture_services(
        &log,
        vec![],
        Ok(ContextLoad {
            history: vec![],
            readable: true,
        }),
        Ok(true),
        Err(backcountry_runtime::adapters::AdapterError::new("not_used")),
        Err(backcountry_runtime::adapters::AdapterError::new("not_used")),
        Ok(vec![]),
        Ok(backcountry_runtime::domain::unknown_fire_result("not_used")),
    );
    let blocked = handle_event(
        &sns_event("+14165550000", "tell me a joke"),
        &capture_config(),
        Some("+14165551234"),
        &mut blocked_services,
    );
    assert_eq!(blocked.status, "ignored");
    assert_eq!(blocked.reason.as_deref(), Some("sender_not_allowed"));
    assert!(!blocked.sms_api_called);
}

#[test]
fn delivery_configuration_accepts_only_safe_combinations() {
    assert!(DeliveryConfig::from_values("true", "capture", "test").is_ok());
    assert!(DeliveryConfig::from_values("false", "live", "production").is_ok());
    assert!(DeliveryConfig::from_values("false", "capture", "production").is_err());
    assert!(DeliveryConfig::from_values("true", "live", "test").is_err());
    assert!(DeliveryConfig::from_values("maybe", "live", "production").is_err());
    assert_eq!(normalized_e164("+1 (416) 555-1234"), "+14165551234");
    assert_eq!(normalized_e164("short"), "");
}

#[test]
fn interpretation_schema_is_strict_and_coordinates_are_provider_safe() {
    let interpretation = parse_interpretation(r#"{"intent":"weather","location_text":"Toronto","current_location_text":"Toronto","coordinates":{"latitude":43.65,"longitude":-79.38},"time_window":"today","activity":"general","location_source":"current"}"#).unwrap();
    assert_eq!(interpretation.location_source, "current");
    assert!(parse_interpretation("```json\n{\"intent\":\"weather\",\"location_text\":null,\"current_location_text\":\"\",\"coordinates\":null,\"time_window\":\"today\",\"activity\":\"general\",\"location_source\":\"none\"}\n```").is_ok());
    assert!(parse_interpretation(r#"{"intent":"weather","location_text":null,"current_location_text":"","coordinates":{"latitude":999,"longitude":0},"time_window":"today","activity":"general","location_source":"none"}"#).is_err());
    assert!(parse_interpretation(r#"{"intent":"weather","location_text":null,"current_location_text":"","coordinates":null,"time_window":"today","activity":"general","location_source":"none","extra":"reject"}"#).is_err());
    let info = parse_interpretation(r#"{"intent":"information_lookup","location_text":"Algonquin","current_location_text":"","coordinates":null,"time_window":null,"activity":null,"location_source":"current"}"#).unwrap();
    assert_eq!(info.time_window, "today");
    assert_eq!(info.activity, "general");
    assert!(parse_interpretation(r#"{"intent":"general","location_text":null,"current_location_text":"","coordinates":null,"time_window":null,"activity":"general","location_source":"none"}"#).is_err());
}

#[test]
fn interpretation_normalization_requires_grounded_current_or_history_locations() {
    let history = vec![backcountry_runtime::models::ContextInteraction {
        input_body: "Weather in Pine Ridge".into(),
        output_body: "Pine Ridge: 12C and clear.".into(),
        created_at: "2026-09-05T11:00#old".into(),
    }];
    let follow_up = backcountry_runtime::models::parse_interpretation(&interpretation(
        "weather",
        Some("Pine Ridge"),
        None,
        "current",
    ))
    .unwrap();
    let normalized = backcountry_runtime::models::normalize_interpretation(
        follow_up,
        "What about tomorrow?",
        &history,
    )
    .unwrap();
    assert_eq!(normalized.location_source, "history");
    assert_eq!(normalized.location_text.as_deref(), Some("Pine Ridge"));
    assert!(backcountry_runtime::models::normalize_interpretation(
        backcountry_runtime::models::parse_interpretation(&interpretation(
            "weather",
            Some("Unknown Place"),
            None,
            "current",
        ))
        .unwrap(),
        "What about tomorrow?",
        &history,
    )
    .is_none());
}

#[test]
fn gsm7_replacement_and_extended_character_cost_stay_within_one_segment() {
    assert_eq!(
        bound_sms("smart ‘quotes’ – degree °", "fallback"),
        "smart 'quotes' - degree"
    );
    assert_eq!(septet_count("[]{}^|~\\"), 16);
    let bounded = bound_sms(&"x".repeat(300), "fallback");
    assert!(septet_count(&bounded) <= 160);
    assert!(!bounded.is_empty());
}

fn interpretation(
    intent: &str,
    location: Option<&str>,
    coordinates: Option<(f64, f64)>,
    source: &str,
) -> String {
    let coordinate_value = coordinates
        .map(|(latitude, longitude)| json!({"latitude": latitude, "longitude": longitude}))
        .unwrap_or(serde_json::Value::Null);
    serde_json::to_string(&json!({
        "intent": intent, "location_text": location, "current_location_text": location.unwrap_or(""),
        "coordinates": coordinate_value, "time_window": "today", "activity": "general", "location_source": source
    })).unwrap()
}

fn weather_periods() -> Vec<backcountry_runtime::models::WeatherPeriod> {
    vec![
        backcountry_runtime::models::WeatherPeriod {
            time: "2026-09-05T12:00".into(),
            temperature_c: 10.0,
            precipitation_probability: 20.0,
            precipitation_mm: 0.0,
            rain_mm: 0.0,
            wind_kmh: 10.0,
            gust_kmh: 15.0,
            weather_code: 1.0,
        },
        backcountry_runtime::models::WeatherPeriod {
            time: "2026-09-06T12:00".into(),
            temperature_c: 8.0,
            precipitation_probability: 80.0,
            precipitation_mm: 2.0,
            rain_mm: 2.0,
            wind_kmh: 25.0,
            gust_kmh: 42.0,
            weather_code: 61.0,
        },
    ]
}

fn base_services(
    log: &CallLog,
    model_responses: Vec<Result<String, backcountry_runtime::adapters::AdapterError>>,
) -> backcountry_runtime::adapters::Services {
    capture_services(
        log,
        model_responses,
        Ok(ContextLoad {
            history: vec![],
            readable: true,
        }),
        Ok(true),
        Err(backcountry_runtime::adapters::AdapterError::new(
            "not_configured",
        )),
        Err(backcountry_runtime::adapters::AdapterError::new(
            "not_configured",
        )),
        Ok(vec![]),
        Ok(backcountry_runtime::domain::unknown_fire_result("not_used")),
    )
}

#[test]
fn capture_matrix_general_routes_and_skips_sms() {
    let log = CallLog::default();
    let mut services = base_services(
        &log,
        vec![
            Ok(interpretation("general", None, None, "none")),
            Ok("A short answer.".into()),
        ],
    );
    let result = handle_event(
        &sns_event("+14165551234", "tell me a joke"),
        &capture_config(),
        Some("+14165551234"),
        &mut services,
    );
    assert_eq!(result.status, "captured");
    assert_eq!(result.response.as_deref(), Some("A short answer."));
    assert_eq!(result.call_counts.get("interpretation"), Some(&1));
    assert_eq!(result.call_counts.get("general"), Some(&1));
    assert_eq!(result.call_counts.get("sms"), None);
    assert!(!result.sms_api_called && !result.sns_published);
}

#[test]
fn capture_matrix_gps_weather_has_two_model_calls_and_bounded_output() {
    let log = CallLog::default();
    let mut services = capture_services(
        &log,
        vec![
            Ok(interpretation(
                "weather",
                None,
                Some((45.64, -78.62)),
                "current",
            )),
            Ok("Use caution near changing conditions.".into()),
        ],
        Ok(ContextLoad {
            history: vec![],
            readable: true,
        }),
        Ok(true),
        Err(backcountry_runtime::adapters::AdapterError::new("not_used")),
        Ok(weather_periods()),
        Ok(vec![]),
        Ok(backcountry_runtime::domain::unknown_fire_result("not_used")),
    );
    let result = handle_event(
        &sns_event("+14165551234", "Weather at 45.64,-78.62"),
        &capture_config(),
        Some("+14165551234"),
        &mut services,
    );
    assert_eq!(result.status, "captured");
    assert_eq!(result.call_counts.get("interpretation"), Some(&1));
    assert_eq!(result.call_counts.get("weather"), Some(&1));
    assert_eq!(result.call_counts.get("weather_advice"), Some(&1));
    assert!(backcountry_runtime::gsm7::septet_count(result.response.as_deref().unwrap()) <= 160);
    assert_eq!(result.location_source, None);
    assert!(!result.sms_api_called && !result.sns_published);
}

#[test]
fn capture_matrix_named_weather_uses_provider_coordinates_only() {
    let log = CallLog::default();
    let candidate = backcountry_runtime::models::LocationCandidate {
        name: "Burnt Island Lake".into(),
        coordinates: backcountry_runtime::models::Coordinates {
            latitude: 45.64,
            longitude: -78.62,
        },
        feature_type: "LAKE".into(),
        region: "Ontario".into(),
        source: "nrcan_geonames".into(),
        score: 1.0,
    };
    let mut services = capture_services(
        &log,
        vec![
            Ok(interpretation(
                "weather",
                Some("Burnt Island Lake"),
                None,
                "current",
            )),
            Ok("Cloudy; keep normal caution.".into()),
        ],
        Ok(ContextLoad {
            history: vec![],
            readable: true,
        }),
        Ok(true),
        Ok(backcountry_runtime::models::LocationResolution {
            candidate: Some(candidate),
            outcome: "resolved".into(),
        }),
        Ok(weather_periods()),
        Ok(vec![]),
        Ok(backcountry_runtime::domain::unknown_fire_result("not_used")),
    );
    let result = handle_event(
        &sns_event("+14165551234", "weather at Burnt Island Lake"),
        &capture_config(),
        Some("+14165551234"),
        &mut services,
    );
    assert_eq!(result.status, "captured");
    assert_eq!(result.call_counts.get("location"), Some(&1));
    assert_eq!(result.call_counts.get("weather"), Some(&1));
    assert_eq!(result.call_counts.get("weather_advice"), Some(&1));
    assert!(!result.sms_api_called && !result.sns_published);
}

#[test]
fn information_lookup_requires_citation_and_grounding_before_second_model_call() {
    let log = CallLog::default();
    let result_item = backcountry_runtime::models::RetrievalResult {
        excerpt: "Arrowhead lists canoe rentals.".into(),
        citation: backcountry_runtime::models::RetrievalCitation {
            park_name: "Arrowhead".into(),
            section: "Facilities".into(),
            source_url: "https://www.ontarioparks.ca/park/arrowhead".into(),
            source_label: "Ontario Parks guide".into(),
        },
        score_millis: 900,
        claims: vec![("canoe_rentals".into(), "yes".into())],
    };
    let mut services = capture_services(
        &log,
        vec![
            Ok(interpretation("information_lookup", None, None, "none")),
            Ok("Arrowhead has canoe rentals.".into()),
        ],
        Ok(ContextLoad {
            history: vec![],
            readable: true,
        }),
        Ok(true),
        Err(backcountry_runtime::adapters::AdapterError::new("not_used")),
        Err(backcountry_runtime::adapters::AdapterError::new("not_used")),
        Ok(vec![result_item]),
        Ok(backcountry_runtime::domain::unknown_fire_result("not_used")),
    );
    let result = handle_event(
        &sns_event("+14165551234", "What facilities are listed?"),
        &capture_config(),
        Some("+14165551234"),
        &mut services,
    );
    assert_eq!(result.status, "captured");
    assert!(result
        .response
        .as_deref()
        .unwrap()
        .contains("Source: Ontario Parks - Arrowhead"));
    assert_eq!(result.call_counts.get("retrieval"), Some(&1));
    assert_eq!(result.call_counts.get("rag_response"), Some(&1));

    let blocked_log = CallLog::default();
    let mut blocked_services = capture_services(
        &blocked_log,
        vec![Ok(interpretation("information_lookup", None, None, "none"))],
        Ok(ContextLoad {
            history: vec![],
            readable: true,
        }),
        Ok(true),
        Err(backcountry_runtime::adapters::AdapterError::new("not_used")),
        Err(backcountry_runtime::adapters::AdapterError::new("not_used")),
        Ok(vec![backcountry_runtime::models::RetrievalResult {
            citation: backcountry_runtime::models::RetrievalCitation {
                park_name: "".into(),
                section: "".into(),
                source_url: "s3://private".into(),
                source_label: "".into(),
            },
            excerpt: "weak".into(),
            score_millis: 900,
            claims: vec![],
        }]),
        Ok(backcountry_runtime::domain::unknown_fire_result("not_used")),
    );
    let blocked_result = handle_event(
        &sns_event("+14165551234", "What facilities are listed?"),
        &capture_config(),
        Some("+14165551234"),
        &mut blocked_services,
    );
    assert_eq!(
        blocked_result.response.as_deref(),
        Some(backcountry_runtime::domain::RAG_UNUSABLE)
    );
    assert_eq!(blocked_result.call_counts.get("rag_response"), None);
}

#[test]
fn rag_claim_contradictions_are_rejected() {
    let citation = backcountry_runtime::models::RetrievalCitation {
        park_name: "Test Park".into(),
        section: "Facilities".into(),
        source_url: "https://www.ontarioparks.ca/park/test".into(),
        source_label: "Ontario Parks guide".into(),
    };
    let result = backcountry_runtime::models::RetrievalResult {
        excerpt: "Rentals - Canoe are listed.".into(),
        citation,
        score_millis: 900,
        claims: vec![("canoe_rentals".into(), "no".into())],
    };
    assert!(!backcountry_runtime::domain::safe_rag_answer(
        "Canoe rentals are available.",
        std::slice::from_ref(&result)
    ));
    assert!(backcountry_runtime::domain::safe_rag_answer(
        "No canoe rentals are listed.",
        std::slice::from_ref(&result)
    ));
}

#[test]
fn information_lookup_rejects_generic_evidence_for_unknown_named_park() {
    let result = backcountry_runtime::models::RetrievalResult {
        excerpt: "Arrowhead lists canoe rentals.".into(),
        citation: backcountry_runtime::models::RetrievalCitation {
            park_name: "Arrowhead Provincial Park".into(),
            section: "Facilities".into(),
            source_url: "https://www.ontarioparks.ca/park/arrowhead".into(),
            source_label: "Ontario Parks guide".into(),
        },
        score_millis: 900,
        claims: vec![("canoe_rentals".into(), "yes".into())],
    };
    assert!(backcountry_runtime::domain::filter_retrieval_for_question(
        "Does NeverListed Park have winter camping?",
        vec![result]
    )
    .is_empty());
}

#[test]
fn time_sensitive_guide_details_redirect_before_rag() {
    assert_eq!(
        backcountry_runtime::domain::current_status_redirect(
            "What are the hours and prices at the Portage Store?"
        ),
        Some("For current park hours, rental/fee prices, or operating details, please check Ontario Parks directly.")
    );
}

#[test]
fn retrieval_evidence_is_bounded_before_model_context() {
    let result = backcountry_runtime::models::RetrievalResult {
        excerpt: "x".repeat(800),
        citation: backcountry_runtime::models::RetrievalCitation {
            park_name: "p".repeat(200),
            section: "s".repeat(200),
            source_url: "https://www.ontarioparks.ca/park/test".into(),
            source_label: "l".repeat(200),
        },
        score_millis: 900,
        claims: std::iter::once(("k".repeat(200), "v".repeat(200)))
            .chain((1..20).map(|index| (format!("k{index}"), format!("v{index}"))))
            .collect(),
    };
    let bounded = backcountry_runtime::domain::normalize_retrieval(vec![result]);
    assert_eq!(bounded[0].excerpt.chars().count(), 520);
    assert_eq!(bounded[0].citation.park_name.chars().count(), 120);
    assert_eq!(bounded[0].claims[0].0.chars().count(), 120);
    assert_eq!(bounded[0].claims.len(), 16);
}

#[test]
fn fire_status_capture_preserves_unknown_and_does_not_use_rag() {
    let log = CallLog::default();
    let mut services = capture_services(
        &log,
        vec![Ok(interpretation(
            "fire_status",
            None,
            Some((43.0, -75.0)),
            "current",
        ))],
        Ok(ContextLoad {
            history: vec![],
            readable: true,
        }),
        Ok(true),
        Err(backcountry_runtime::adapters::AdapterError::new("not_used")),
        Err(backcountry_runtime::adapters::AdapterError::new("not_used")),
        Ok(vec![]),
        Ok(backcountry_runtime::domain::unknown_fire_result(
            "park_not_found",
        )),
    );
    let result = handle_event(
        &sns_event("+14165551234", "fire status at 43.0,-75.0"),
        &capture_config(),
        Some("+14165551234"),
        &mut services,
    );
    assert_eq!(result.status, "captured");
    assert!(result
        .response
        .as_deref()
        .unwrap()
        .starts_with("Fire status unknown"));
    assert_eq!(result.call_counts.get("fire_ban"), Some(&1));
    assert_eq!(result.call_counts.get("retrieval"), None);
}

#[test]
fn duplicate_and_malformed_paths_stop_before_second_side_effect() {
    let duplicate_log = CallLog::default();
    let mut duplicate_services = capture_services(
        &duplicate_log,
        vec![Ok(interpretation("general", None, None, "none"))],
        Ok(ContextLoad {
            history: vec![],
            readable: true,
        }),
        Ok(false),
        Err(backcountry_runtime::adapters::AdapterError::new("not_used")),
        Err(backcountry_runtime::adapters::AdapterError::new("not_used")),
        Ok(vec![]),
        Ok(backcountry_runtime::domain::unknown_fire_result("not_used")),
    );
    let duplicate = handle_event(
        &sns_event("+14165551234", "tell me a joke"),
        &capture_config(),
        Some("+14165551234"),
        &mut duplicate_services,
    );
    assert_eq!(duplicate.reason.as_deref(), Some("duplicate_delivery"));
    assert_eq!(duplicate.call_counts, BTreeMap::new());

    let malformed_log = CallLog::default();
    let mut malformed_services = base_services(&malformed_log, vec![Ok("not-json".into())]);
    let malformed = handle_event(
        &sns_event("+14165551234", "weather"),
        &capture_config(),
        Some("+14165551234"),
        &mut malformed_services,
    );
    assert_eq!(malformed.status, "captured");
    assert_eq!(
        malformed.response.as_deref(),
        Some(backcountry_runtime::domain::WEATHER_EXTRACTION_FALLBACK)
    );
    assert_eq!(malformed.call_counts.get("interpretation"), Some(&1));
    assert_eq!(malformed.call_counts.get("general"), None);
}

#[test]
fn fire_snapshot_wkt_holes_multipolygons_and_freshness_fail_closed() {
    let donut = "POLYGON ((0 0, 10 0, 10 10, 0 10, 0 0), (2 2, 8 2, 8 8, 2 8, 2 2))";
    assert_eq!(
        backcountry_runtime::domain::point_in_wkt(1.0, 1.0, donut).unwrap(),
        "inside"
    );
    assert_eq!(
        backcountry_runtime::domain::point_in_wkt(5.0, 5.0, donut).unwrap(),
        "outside"
    );
    assert_eq!(
        backcountry_runtime::domain::point_in_wkt(2.0, 5.0, donut).unwrap(),
        "boundary"
    );
    let multi =
        "MULTIPOLYGON (((20 0, 30 0, 30 10, 20 10, 20 0)), ((40 0, 50 0, 50 10, 40 10, 40 0)))";
    assert_eq!(
        backcountry_runtime::domain::point_in_wkt(5.0, 25.0, multi).unwrap(),
        "inside"
    );
    assert!(backcountry_runtime::domain::point_in_wkt(
        1.0,
        1.0,
        "POLYGON ((0 0, 2 2, 0 2, 2 0, 0 0))"
    )
    .is_err());

    let snapshot: backcountry_runtime::models::FireBanSnapshot = serde_json::from_str(
        include_str!("../../tests/fixtures/stage-9-2-fire-ban-snapshot.json"),
    )
    .unwrap();
    let now: DateTime<FixedOffset> = "2026-08-21T12:00:00Z".parse().unwrap();
    let active = backcountry_runtime::domain::lookup_snapshot(
        &snapshot,
        backcountry_runtime::models::Coordinates {
            latitude: 45.15,
            longitude: -79.35,
        },
        now,
        14,
    );
    assert_eq!(active.status, "fire_ban");
    assert_eq!(
        active.park_name.as_deref(),
        Some("Active Fixture Provincial Park")
    );
    let outside = backcountry_runtime::domain::lookup_snapshot(
        &snapshot,
        backcountry_runtime::models::Coordinates {
            latitude: 43.0,
            longitude: -75.0,
        },
        now,
        14,
    );
    assert_eq!(outside.uncertainty.as_deref(), Some("park_not_found"));
    let stale_now: DateTime<FixedOffset> = "2026-09-10T12:00:00Z".parse().unwrap();
    assert_eq!(
        backcountry_runtime::domain::lookup_snapshot(
            &snapshot,
            backcountry_runtime::models::Coordinates {
                latitude: 45.15,
                longitude: -79.35
            },
            stale_now,
            14
        )
        .uncertainty
        .as_deref(),
        Some("stale_snapshot")
    );
}
