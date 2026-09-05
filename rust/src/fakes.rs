//! Deterministic, side-effect-free adapters for the capture harness.

use crate::{adapters::*, models::*};
use std::{
    cell::RefCell,
    collections::{BTreeMap, VecDeque},
    rc::Rc,
};

#[derive(Clone, Default)]
pub struct CallLog(pub Rc<RefCell<Vec<String>>>);
impl CallLog {
    pub fn record(&self, operation: &str) {
        self.0.borrow_mut().push(operation.to_owned());
    }
    pub fn operations(&self) -> Vec<String> {
        self.0.borrow().clone()
    }
}

pub struct ScriptedModel {
    pub log: CallLog,
    pub responses: VecDeque<Result<String, AdapterError>>,
}
impl ModelClient for ScriptedModel {
    fn converse(&mut self, request: ModelRequest) -> Result<String, AdapterError> {
        self.log.record(request.operation.as_str());
        self.responses
            .pop_front()
            .unwrap_or_else(|| Err(AdapterError::new("unavailable")))
    }
}

pub struct ScriptedLocation {
    pub log: CallLog,
    pub response: Result<LocationResolution, AdapterError>,
}
impl LocationResolver for ScriptedLocation {
    fn resolve(&mut self, _query: &str) -> Result<LocationResolution, AdapterError> {
        self.log.record("location");
        self.response.clone()
    }
}

pub struct ScriptedWeather {
    pub log: CallLog,
    pub response: Result<Vec<WeatherPeriod>, AdapterError>,
}
impl WeatherProvider for ScriptedWeather {
    fn forecast(&mut self, _coordinates: Coordinates) -> Result<Vec<WeatherPeriod>, AdapterError> {
        self.log.record("weather");
        self.response.clone()
    }
}

pub struct ScriptedContext {
    pub log: CallLog,
    pub load: Result<ContextLoad, AdapterError>,
    pub reserve: Result<bool, AdapterError>,
    pub complete: Result<(), AdapterError>,
}
impl ContextStore for ScriptedContext {
    fn load(&mut self, _sender: &str) -> Result<ContextLoad, AdapterError> {
        self.log.record("context_read");
        self.load.clone()
    }
    fn reserve(
        &mut self,
        _sender: &str,
        _message_id: &str,
        _created_at: &str,
        _input: &str,
    ) -> Result<bool, AdapterError> {
        self.log.record("context_reserve");
        self.reserve.clone()
    }
    fn complete(
        &mut self,
        _sender: &str,
        _message_id: &str,
        _created_at: &str,
        _input: &str,
        _output: &str,
    ) -> Result<(), AdapterError> {
        self.log.record("context_complete");
        self.complete.clone()
    }
}

pub struct ScriptedRetriever {
    pub log: CallLog,
    pub response: Result<Vec<RetrievalResult>, AdapterError>,
}
impl Retriever for ScriptedRetriever {
    fn retrieve(&mut self, _question: &str) -> Result<Vec<RetrievalResult>, AdapterError> {
        self.log.record("retrieval");
        self.response.clone()
    }
}

pub struct ScriptedFireBan {
    pub log: CallLog,
    pub response: Result<FireBanResult, AdapterError>,
}
impl FireBanProvider for ScriptedFireBan {
    fn lookup(&mut self, _coordinates: Coordinates) -> Result<FireBanResult, AdapterError> {
        self.log.record("fire_ban");
        self.response.clone()
    }
}

pub struct RecordingSms {
    pub log: CallLog,
    pub calls: Vec<(String, String)>,
}
impl SmsSender for RecordingSms {
    fn send(&mut self, destination: &str, body: &str) -> Result<(), AdapterError> {
        self.log.record("sms");
        self.calls.push((destination.to_owned(), body.to_owned()));
        Ok(())
    }
}

#[derive(Default)]
pub struct RecordingTelemetry {
    pub events: Vec<TelemetryEvent>,
    pub counts: BTreeMap<String, usize>,
}
impl TelemetrySink for RecordingTelemetry {
    fn emit(&mut self, event: TelemetryEvent) {
        if event.event == "adapter_call" {
            if let Some(outcome) = &event.outcome {
                *self.counts.entry(outcome.clone()).or_insert(0) += 1;
            }
        }
        self.events.push(event);
    }
    fn snapshot(&self) -> BTreeMap<String, usize> {
        self.counts.clone()
    }
}

#[allow(clippy::too_many_arguments)]
pub fn capture_services(
    log: &CallLog,
    model_responses: Vec<Result<String, AdapterError>>,
    context_load: Result<ContextLoad, AdapterError>,
    context_reserve: Result<bool, AdapterError>,
    location: Result<LocationResolution, AdapterError>,
    weather: Result<Vec<WeatherPeriod>, AdapterError>,
    retrieval: Result<Vec<RetrievalResult>, AdapterError>,
    fire_ban: Result<FireBanResult, AdapterError>,
) -> Services {
    Services {
        model: Box::new(ScriptedModel {
            log: log.clone(),
            responses: model_responses.into(),
        }),
        location: Box::new(ScriptedLocation {
            log: log.clone(),
            response: location,
        }),
        weather: Box::new(ScriptedWeather {
            log: log.clone(),
            response: weather,
        }),
        context: Box::new(ScriptedContext {
            log: log.clone(),
            load: context_load,
            reserve: context_reserve,
            complete: Ok(()),
        }),
        retriever: Box::new(ScriptedRetriever {
            log: log.clone(),
            response: retrieval,
        }),
        fire_ban: Box::new(ScriptedFireBan {
            log: log.clone(),
            response: fire_ban,
        }),
        sms: Box::new(RecordingSms {
            log: log.clone(),
            calls: Vec::new(),
        }),
        telemetry: Box::new(RecordingTelemetry::default()),
    }
}
