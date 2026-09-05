//! Deterministic routing, provider-result validation, weather guidance, and fire-ban geometry.

use crate::{
    adapters::{ModelOperation, ModelRequest},
    models::{
        ContextInteraction, Coordinates, FireBanResult, FireBanSnapshot, RetrievalCitation,
        RetrievalResult, WeatherPeriod,
    },
};
use chrono::{DateTime, FixedOffset, NaiveDate};
use regex::Regex;
use serde::Serialize;
use std::{
    collections::{BTreeMap, HashSet},
    sync::OnceLock,
};

pub const MAX_SMS_CHARS: usize = 160;
pub const FALLBACK_REPLY: &str = "The AI assistant is temporarily unavailable. Please try again.";
pub const WEATHER_EXTRACTION_FALLBACK: &str =
    "I couldn't understand that weather request. Please include GPS coordinates or a named place.";
pub const WEATHER_LOCATION_PROMPT: &str =
    "Please include GPS coordinates or a named place, for example: weather at 45.62,-78.42.";
pub const WEATHER_COORDINATE_FALLBACK: &str =
    "Those coordinates need correction. Please send latitude and longitude, e.g. 45.62,-78.42.";
pub const WEATHER_LOCATION_NOT_FOUND: &str =
    "I couldn't verify that place. Please send GPS coordinates or more location detail.";
pub const WEATHER_LOCATION_AMBIGUOUS: &str =
    "That place is ambiguous. Please send GPS coordinates or add a nearby park or town.";
pub const WEATHER_LOCATION_UNAVAILABLE: &str =
    "Location lookup is unavailable right now. Please try GPS coordinates later.";
pub const WEATHER_PROVIDER_FALLBACK: &str =
    "Weather data is unavailable right now. Please try again shortly.";
pub const WEATHER_ADVICE_FALLBACK: &str =
    "Weather is available, but advice is unavailable. Please use caution.";
pub const CURRENT_DATA_LIMITATION_REPLY: &str = "I don't have real-time news or stats. I can provide weather, fire status, and Ontario Parks guide information.";
pub const RAG_RETRIEVAL_FAILURE: &str =
    "I couldn't retrieve guide evidence right now. Please check Ontario Parks directly.";
pub const RAG_RESPONSE_FAILURE: &str =
    "I couldn't summarize the guide evidence right now. Please check Ontario Parks directly.";
pub const RAG_UNUSABLE: &str =
    "The Ontario Parks guide does not establish that answer. Please check Ontario Parks directly.";

pub fn model_request(
    operation: ModelOperation,
    text: &str,
    history: &[ContextInteraction],
    evidence: Option<String>,
    max_tokens: u16,
    temperature: f32,
) -> ModelRequest {
    ModelRequest {
        operation,
        user_text: text.to_owned(),
        history: history.to_vec(),
        evidence,
        max_tokens,
        temperature,
    }
}

pub enum Route {
    General {
        interpretation: crate::models::Interpretation,
    },
    Clarify {
        interpretation: crate::models::Interpretation,
    },
    InformationLookup {
        interpretation: crate::models::Interpretation,
    },
    Weather {
        interpretation: crate::models::Interpretation,
    },
    FireStatus {
        interpretation: crate::models::Interpretation,
    },
}
impl Route {
    pub fn intent(&self) -> &'static str {
        match self {
            Self::General { .. } => "general",
            Self::Clarify { .. } => "unclear",
            Self::InformationLookup { .. } => "information_lookup",
            Self::Weather { .. } => "weather",
            Self::FireStatus { .. } => "fire_status",
        }
    }
}

pub fn route(text: &str, interpretation: crate::models::Interpretation) -> Route {
    if contains_weather_term(text) || contains_weather_activity(text) {
        return Route::Weather { interpretation };
    }
    if contains_fire_term(text) {
        return Route::FireStatus { interpretation };
    }
    match interpretation.intent.as_str() {
        "weather" => Route::Weather { interpretation },
        "fire_status" => Route::FireStatus { interpretation },
        "information_lookup" => Route::InformationLookup { interpretation },
        "unclear" => Route::Clarify { interpretation },
        _ => Route::General { interpretation },
    }
}

pub fn current_status_redirect(text: &str) -> Option<&'static str> {
    let lower = text.to_ascii_lowercase();
    let current = Regex::new(r"\b(open|closed|closure|closing|reservation|reservations|booking?)\b|\b(available|availability)\b.{0,35}\b(campsites?|sites?)\b|\b(campsites?|sites?)\b.{0,35}\b(available|availability|open|closed)\b").unwrap();
    if current.is_match(&lower) {
        return Some("For current openings, closures, reservations, or availability, please check Ontario Parks directly.");
    }
    if contains_weather_term(text) || contains_fire_term(text) {
        return None;
    }
    let stable =
        Regex::new(r"\b(facilit(y|ies)|canoe rentals?|rentals?|equipment|amenities|activities)\b")
            .unwrap();
    let current_words = Regex::new(r"\b(today|tomorrow|tonight|weekend|now|currently|this week|site|sites|campsite|campsites)\b").unwrap();
    if (lower.contains("open") || lower.contains("available") || lower.contains("campsite"))
        && !(stable.is_match(&lower) && !current_words.is_match(&lower))
    {
        return Some("For current openings, closures, reservations, or availability, please check Ontario Parks directly.");
    }
    if Regex::new(r"\b(today|tomorrow|tonight|this weekend|weekend|this week)\b")
        .unwrap()
        .is_match(&lower)
        && Regex::new(r"\b(camp|camping|stay|visit|access)\b")
            .unwrap()
            .is_match(&lower)
    {
        return Some("For current openings, closures, reservations, or availability, please check Ontario Parks directly.");
    }
    None
}

pub fn current_news_question(text: &str) -> bool {
    let lower = text.to_ascii_lowercase();
    Regex::new(r"\b(news|headlines?|current events?|breaking news|statistics?|stats)\b")
        .unwrap()
        .is_match(&lower)
        || Regex::new(r"\bwhat happened\b[^?!.]{0,50}\b(today|now|latest)\b")
            .unwrap()
            .is_match(&lower)
        || Regex::new(r"\b(latest|current)\b[^?!.]{0,35}\b(news|events?|stats|statistics?)\b")
            .unwrap()
            .is_match(&lower)
}
pub fn contains_weather_term(text: &str) -> bool {
    Regex::new(r"\b(weather|forecast|temperature|rain|wind|snow|sunny|cold|warm)\b")
        .unwrap()
        .is_match(&text.to_ascii_lowercase())
}
pub fn contains_fire_term(text: &str) -> bool {
    Regex::new(r"\b(fire|fire ban|burn ban|campfire)\b")
        .unwrap()
        .is_match(&text.to_ascii_lowercase())
}
pub fn contains_weather_activity(text: &str) -> bool {
    let lower = text.to_ascii_lowercase();
    Regex::new(r"\b(cross(ing)?|paddl(e|ing)|canoe|kayak|tarp|shelter|camp(ing)?|sleep(ing)?|hike|hiking)\b").unwrap().is_match(&lower)
        && Regex::new(r"\b(can i|should i|planning|plan to|what should|watch for|conditions?|suitable|okay to|ok to)\b").unwrap().is_match(&lower)
}

static COORDINATE_PATTERN: OnceLock<Regex> = OnceLock::new();
pub fn parse_coordinates(text: &str) -> Option<Coordinates> {
    let pattern = COORDINATE_PATTERN.get_or_init(|| Regex::new(r"(?i)(?:\b(?:lat(?:itude)?|y)\s*[:=]?\s*)?(?P<lat>[+-]?\d{1,3}(?:\.\d+)?)\s*(?:°|º)?\s*(?P<lat_h>[NS])?\s*(?:,|/|;|\s+)\s*(?:\b(?:lon(?:gitude)?|lng|x)\s*[:=]?\s*)?(?P<lon>[+-]?\d{1,3}(?:\.\d+)?)\s*(?:°|º)?\s*(?P<lon_h>[EW])?\b").unwrap());
    let matched = pattern.captures(text)?;
    let latitude = coordinate_value(
        &matched["lat"],
        matched.name("lat_h").map(|value| value.as_str()),
        "NS",
    )
    .ok()?;
    let longitude = coordinate_value(
        &matched["lon"],
        matched.name("lon_h").map(|value| value.as_str()),
        "EW",
    )
    .ok()?;
    let coordinates = Coordinates {
        latitude,
        longitude,
    };
    coordinates.is_valid().then_some(coordinates)
}
fn coordinate_value(value: &str, hemisphere: Option<&str>, valid: &str) -> Result<f64, ()> {
    let number = value.parse::<f64>().map_err(|_| ())?;
    if let Some(hemisphere) = hemisphere {
        if !valid.contains(hemisphere.to_ascii_uppercase().as_str()) || number < 0.0 {
            return Err(());
        }
        if matches!(hemisphere.to_ascii_uppercase().as_str(), "S" | "W") {
            return Ok(-number);
        }
    }
    Ok(number)
}
pub fn contains_coordinate_attempt(text: &str) -> bool {
    parse_coordinates(text).is_some()
        || Regex::new(r"\b(lat(itude)?|lon(gitude)?|lng)\b|[0-9]{1,3}(?:\.\d+)?\s*[NS]\b")
            .unwrap()
            .is_match(text)
}

pub fn history_location(history: &[ContextInteraction]) -> String {
    let pattern = Regex::new(r"\b(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b").unwrap();
    history
        .iter()
        .rev()
        .flat_map(|item| [item.input_body.as_str(), item.output_body.as_str()])
        .find_map(|text| {
            pattern
                .find_iter(text)
                .max_by_key(|value| value.as_str().len())
                .map(|value| value.as_str().to_owned())
        })
        .unwrap_or_default()
}

pub fn select_weather_period(
    periods: &[WeatherPeriod],
    time_window: &str,
) -> Option<WeatherPeriod> {
    let first_day = periods.first()?.time.get(..10).unwrap_or("");
    let tomorrow = time_window.to_ascii_lowercase().contains("tomorrow");
    let candidates: Vec<&WeatherPeriod> = if tomorrow {
        let filtered: Vec<_> = periods
            .iter()
            .filter(|period| period.time.get(..10).unwrap_or("") > first_day)
            .collect();
        if filtered.is_empty() {
            periods.iter().collect()
        } else {
            filtered
        }
    } else {
        periods.iter().collect()
    };
    let desired = if time_window.to_ascii_lowercase().contains("morning") {
        Some(9)
    } else if ["noon", "midday", "mid day"]
        .iter()
        .any(|term| time_window.to_ascii_lowercase().contains(term))
    {
        Some(12)
    } else if time_window.to_ascii_lowercase().contains("tonight") {
        Some(18)
    } else {
        None
    };
    desired
        .and_then(|hour| {
            candidates
                .iter()
                .find(|period| period.time.get(11..13) == Some(&format!("{hour:02}")))
                .copied()
        })
        .or_else(|| candidates.first().copied())
        .cloned()
}
pub fn trip_guidance(weather: &WeatherPeriod, activity: &str) -> Vec<String> {
    let lower = activity.to_ascii_lowercase();
    let open_water = ["cano", "paddl", "kayak", "cross"]
        .iter()
        .any(|term| lower.contains(term));
    let camping = ["camp", "tarp", "shelter", "sleep"]
        .iter()
        .any(|term| lower.contains(term));
    let mut guidance = Vec::new();
    if open_water && weather.gust_kmh >= 40.0 {
        guidance.push(
            if lower.contains("cano") {
                "Avoid open-water canoeing; gusts are high."
            } else {
                "Avoid exposed open-water crossings; gusts are high."
            }
            .into(),
        );
    } else if open_water && (weather.gust_kmh >= 30.0 || weather.wind_kmh >= 25.0) {
        guidance.push("Stay near shore; wind may build on open water.".into());
    } else if open_water {
        guidance
            .push("Watch wind, rain, and visibility; stay near shore if conditions worsen.".into());
    }
    if camping && (weather.precipitation_probability >= 60.0 || weather.precipitation_mm >= 1.0) {
        guidance.push("Set the tarp before rain.".into());
    }
    if weather.temperature_c <= 5.0 {
        guidance.push("Plan warm, dry layers for cold conditions.".into());
    }
    if guidance.is_empty() {
        guidance
            .push("No major weather trigger in this forecast hour; keep normal caution.".into());
    }
    if open_water && weather.gust_kmh >= 30.0 {
        guidance.push("Avoid exposed crossings if conditions worsen.".into());
    }
    guidance
}
pub fn deterministic_weather_summary(weather: &WeatherPeriod, guidance: &[String]) -> String {
    format!(
        "{:.0}C, rain {:.0}%, gusts {:.0} km/h. {}",
        weather.temperature_c,
        weather.precipitation_probability,
        weather.gust_kmh,
        guidance
            .first()
            .map(String::as_str)
            .unwrap_or("Keep normal caution.")
    )
}

#[derive(Serialize)]
struct WeatherEvidence<'a> {
    location: &'a str,
    coordinates: Coordinates,
    weather: &'a WeatherPeriod,
    guidance: &'a [String],
    fire_ban: Option<&'a FireBanResult>,
}
pub fn weather_evidence(
    label: &str,
    coordinates: Coordinates,
    weather: &WeatherPeriod,
    guidance: &[String],
    fire: Option<&FireBanResult>,
) -> String {
    serde_json::to_string(&WeatherEvidence {
        location: label,
        coordinates,
        weather,
        guidance,
        fire_ban: fire,
    })
    .unwrap_or_else(|_| "{}".into())
}
pub fn contains_absolute_safety_claim(text: &str) -> bool {
    Regex::new(r"\b(safe|safely|guarantee(d)?|no risk)\b")
        .unwrap()
        .is_match(&text.to_ascii_lowercase())
}
pub fn contains_stale_history_location(
    text: &str,
    history: &[ContextInteraction],
    verified: &str,
) -> bool {
    let lower = text.to_ascii_lowercase();
    !history_location(history).eq_ignore_ascii_case(verified)
        && !history_location(history).is_empty()
        && lower.contains(&history_location(history).to_ascii_lowercase())
}

pub fn normalize_retrieval(results: Vec<RetrievalResult>) -> Vec<RetrievalResult> {
    results
        .into_iter()
        .map(|mut result| {
            result.excerpt = bounded_text(&result.excerpt, 520);
            result.citation.park_name = bounded_text(&result.citation.park_name, 120);
            result.citation.section = bounded_text(&result.citation.section, 120);
            result.citation.source_url = bounded_text(&result.citation.source_url, 120);
            result.citation.source_label = bounded_text(&result.citation.source_label, 120);
            result.claims = result
                .claims
                .into_iter()
                .take(16)
                .map(|(key, value)| (bounded_text(&key, 120), bounded_text(&value, 120)))
                .collect();
            result
        })
        .filter(|result| !result.excerpt.is_empty() && result.score_millis >= 400)
        .take(3)
        .collect()
}

fn bounded_text(value: &str, limit: usize) -> String {
    value.chars().take(limit).collect()
}
pub fn usable_retrieval(results: &[RetrievalResult]) -> bool {
    !results.is_empty()
        && results.iter().all(|result| {
            !result.citation.park_name.is_empty()
                && !result.citation.section.is_empty()
                && result
                    .citation
                    .source_url
                    .starts_with("https://www.ontarioparks.ca/park/")
                && !result.citation.source_label.is_empty()
        })
        && !conflicting_claims(results)
}
fn conflicting_claims(results: &[RetrievalResult]) -> bool {
    let mut values: BTreeMap<(String, String, String), HashSet<String>> = BTreeMap::new();
    for result in results {
        for (key, value) in &result.claims {
            values
                .entry((
                    result.citation.park_name.to_ascii_lowercase(),
                    result.citation.section.to_ascii_lowercase(),
                    key.clone(),
                ))
                .or_default()
                .insert(value.clone());
        }
    }
    values.values().any(|value| value.len() > 1)
}
pub fn safe_rag_answer(answer: &str, results: &[RetrievalResult]) -> bool {
    let normalized = normalize(answer);
    if normalized.is_empty() || Regex::new(r"\b(today|tomorrow|tonight|currently|right now|open|closed|closure|available|availability|reservation|reservations|booking?|campsites?|fire ban|weather)\b").unwrap().is_match(&normalized.to_ascii_lowercase()) { return false; }
    if answer_conflicts_with_claims(&normalized, results) {
        return false;
    }
    if results.iter().any(|result| {
        Regex::new(r"\b(?:not|no|without|doesn't|does not)\b")
            .unwrap()
            .is_match(&result.excerpt.to_ascii_lowercase())
    }) && !Regex::new(r"\b(?:not|no|without|doesn't|does not)\b")
        .unwrap()
        .is_match(&normalized.to_ascii_lowercase())
    {
        return false;
    }
    let evidence: HashSet<String> = words(
        &results
            .iter()
            .map(|result| result.excerpt.as_str())
            .collect::<Vec<_>>()
            .join(" "),
    );
    let answer_words = words(&normalized);
    let overlap = answer_words.intersection(&evidence).count();
    answer_words.len() >= 2 && overlap >= 2 && (overlap as f64 / answer_words.len() as f64) >= 0.45
}
fn answer_conflicts_with_claims(answer: &str, results: &[RetrievalResult]) -> bool {
    let lowered = answer.to_ascii_lowercase();
    let negative = Regex::new(r"\b(?:not|no|without|doesn't|does not)\b").unwrap();
    for result in results {
        for (key, value) in &result.claims {
            let phrase = match key.as_str() {
                "backcountry_camping" => r"backcountry camping",
                "winter_camping" => r"winter camping",
                "car_camping" => r"car camping",
                "walk_in_camping" => r"walk[- ]in camping",
                "canoe_rentals" => r"canoe rentals?",
                "boat_launch" => r"boat launch(?:es)?",
                "canoeing" => r"canoeing",
                _ => continue,
            };
            let pattern = Regex::new(phrase).unwrap();
            let Some(found) = pattern.find(&lowered) else {
                continue;
            };
            let prefix_start = found.start().saturating_sub(28);
            let prefix = &lowered[prefix_start..found.start()];
            let answer_value = if negative.is_match(prefix) {
                "no"
            } else {
                "yes"
            };
            if answer_value != value {
                return true;
            }
        }
    }
    false
}
fn words(value: &str) -> HashSet<String> {
    let ignored = [
        "about", "and", "are", "based", "does", "for", "from", "guide", "has", "have", "is", "it",
        "listed", "of", "on", "or", "park", "parks", "that", "the", "this", "to", "what", "with",
        "yes",
    ];
    Regex::new(r"[A-Za-z]{3,}")
        .unwrap()
        .find_iter(value)
        .map(|word| word.as_str().to_ascii_lowercase())
        .filter(|word| !ignored.contains(&word.as_str()))
        .collect()
}
pub fn citation_suffix(citation: &RetrievalCitation) -> String {
    let label = format!(
        "Source: {}",
        if citation.park_name.is_empty() {
            citation.source_label.clone()
        } else {
            format!("Ontario Parks - {}", citation.park_name)
        }
    );
    let candidate = format!("{} {}", label, citation.source_url);
    if citation.source_url.starts_with("https://") && candidate.chars().count() <= 80 {
        candidate
    } else {
        label
    }
}
pub fn retrieval_evidence(results: &[RetrievalResult]) -> String {
    serde_json::to_string(results).unwrap_or_else(|_| "[]".into())
}

pub fn normalize(text: &str) -> String {
    crate::gsm7::normalize(text)
}
pub fn bound_sms(text: &str, fallback: &str) -> String {
    crate::gsm7::bound_sms(text, fallback)
}
pub fn truncate_septets(text: &str, budget: usize) -> String {
    let normalized = normalize(text);
    let mut output = String::new();
    let mut used = 0;
    for character in normalized.chars() {
        let cost = if "^{}\\[~]|".contains(character) {
            2
        } else {
            1
        };
        if used + cost > budget {
            break;
        }
        output.push(character);
        used += cost;
    }
    output.trim_end().to_owned()
}
pub fn septet_count(text: &str) -> usize {
    crate::gsm7::septet_count(text)
}

pub fn fire_ban_sms(result: &FireBanResult) -> String {
    match result.status.as_str() { "fire_ban" => format!("{}: Ontario Parks fire ban active as of {}. Verify alerts before travel.", result.park_name.as_deref().unwrap_or("This park"), result.source_as_of.as_deref().unwrap_or("snapshot date")), "no_current_fire_ban_record" => format!("{}: no Ontario Parks fire-ban record in this snapshot. Verify current alerts; this does not mean fires are allowed.", result.park_name.as_deref().unwrap_or("This park")), _ => format!("Fire status unknown for {}; verify Ontario Parks alerts.", result.park_name.as_deref().unwrap_or("this point")) }
}
pub fn unknown_fire_result(reason: &str) -> FireBanResult {
    FireBanResult {
        park_name: None,
        jurisdiction: "Ontario Parks".into(),
        status: "unknown".into(),
        source_as_of: None,
        retrieved_at: None,
        source_url: Some("https://www.ontarioparks.ca/alerts".into()),
        source_hash: None,
        snapshot_id: None,
        freshness: "missing".into(),
        boundary: "invalid".into(),
        uncertainty: Some(reason.into()),
    }
}

type Point = (f64, f64);
type Ring = Vec<Point>;
type Polygon = Vec<Ring>;
#[derive(Debug)]
enum Node {
    Point(Point),
    Group(Vec<Node>),
}
pub fn point_in_wkt(latitude: f64, longitude: f64, wkt: &str) -> Result<&'static str, String> {
    let polygons = parse_wkt(wkt).map_err(|_| "invalid_geometry".to_owned())?;
    let point = (longitude, latitude);
    if polygons
        .iter()
        .flat_map(|polygon| polygon.iter())
        .any(|ring| on_segment(point, ring))
    {
        return Ok("boundary");
    }
    Ok(
        if polygons
            .iter()
            .any(|polygon| inside_polygon(point, polygon))
        {
            "inside"
        } else {
            "outside"
        },
    )
}
fn parse_wkt(wkt: &str) -> Result<Vec<Polygon>, String> {
    let token_re = Regex::new(r"[A-Za-z]+|[-+]?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?|[(),]").unwrap();
    let tokens: Vec<&str> = token_re.find_iter(wkt).map(|m| m.as_str()).collect();
    if tokens.len() < 2
        || !matches!(
            tokens[0].to_ascii_uppercase().as_str(),
            "POLYGON" | "MULTIPOLYGON"
        )
        || tokens.last() != Some(&")")
    {
        return Err("invalid_geometry".into());
    }
    let kind = tokens[0].to_ascii_uppercase();
    let mut index = 1;
    let parsed = parse_group(&tokens, &mut index)?;
    if index != tokens.len() {
        return Err("invalid_geometry".into());
    }
    let polygon_nodes = match (kind.as_str(), parsed) {
        ("POLYGON", Node::Group(rings)) => vec![rings],
        ("MULTIPOLYGON", Node::Group(polygons)) => polygons
            .into_iter()
            .map(|node| match node {
                Node::Group(rings) => Ok(rings),
                _ => Err("invalid_geometry".into()),
            })
            .collect::<Result<Vec<_>, String>>()?,
        _ => return Err("invalid_geometry".into()),
    };
    let mut output = Vec::new();
    for polygon in polygon_nodes {
        let mut rings_out = Vec::new();
        for ring in polygon {
            let Node::Group(points) = ring else {
                return Err("hole_outside_shell".into());
            };
            let points = points
                .into_iter()
                .map(|node| match node {
                    Node::Point(point) => Ok(point),
                    _ => Err("invalid_geometry".into()),
                })
                .collect::<Result<Ring, String>>()?;
            validate_ring(&points)?;
            rings_out.push(points);
        }
        if rings_out.is_empty() {
            return Err("invalid_geometry".into());
        }
        output.push(rings_out);
    }
    validate_topology(&output)?;
    Ok(output)
}
fn parse_group(tokens: &[&str], index: &mut usize) -> Result<Node, String> {
    if tokens.get(*index) != Some(&"(") {
        return Err("invalid_geometry".into());
    }
    *index += 1;
    let mut values = Vec::new();
    while *index < tokens.len() && tokens[*index] != ")" {
        if tokens[*index] == "(" {
            values.push(parse_group(tokens, index)?);
        } else {
            let x = tokens
                .get(*index)
                .ok_or("invalid_geometry")?
                .parse::<f64>()
                .map_err(|_| "invalid_geometry")?;
            let y = tokens
                .get(*index + 1)
                .ok_or("invalid_geometry")?
                .parse::<f64>()
                .map_err(|_| "invalid_geometry")?;
            *index += 2;
            values.push(Node::Point((x, y)));
        }
        if *index < tokens.len() && tokens[*index] == "," {
            *index += 1;
        } else if tokens.get(*index) != Some(&")") {
            return Err("invalid_geometry".into());
        }
    }
    if tokens.get(*index) != Some(&")") {
        return Err("invalid_geometry".into());
    }
    *index += 1;
    Ok(Node::Group(values))
}
fn validate_ring(ring: &Ring) -> Result<(), String> {
    if ring.len() < 4
        || ring.first() != ring.last()
        || ring.iter().any(|(x, y)| {
            !x.is_finite()
                || !y.is_finite()
                || !(-180.0..=180.0).contains(x)
                || !(-90.0..=90.0).contains(y)
        })
    {
        return Err("invalid_geometry".into());
    }
    let area = ring
        .windows(2)
        .map(|pair| pair[0].0 * pair[1].1 - pair[1].0 * pair[0].1)
        .sum::<f64>()
        .abs()
        / 2.0;
    if area <= 1e-12 || ring.windows(2).any(|pair| pair[0] == pair[1]) {
        return Err("invalid_geometry".into());
    }
    let segments: Vec<_> = ring.windows(2).collect();
    for (first_index, first) in segments.iter().enumerate() {
        for (second_index, second) in segments.iter().enumerate().skip(first_index + 1) {
            if second_index == first_index + 1
                || first_index == 0 && second_index == segments.len() - 1
            {
                continue;
            }
            if segments_intersect(first, second) {
                return Err("invalid_geometry".into());
            }
        }
    }
    Ok(())
}
fn validate_topology(polygons: &[Polygon]) -> Result<(), String> {
    for polygon in polygons {
        let outer = &polygon[0];
        for hole in polygon.iter().skip(1) {
            if rings_intersect(hole, outer) || ring_relation(hole, outer) != "inside" {
                return Err("invalid_geometry".into());
            }
        }
        for (i, first) in polygon.iter().enumerate().skip(1) {
            for second in polygon.iter().skip(i + 1) {
                if rings_intersect(first, second)
                    || inside(first[0], second)
                    || inside(second[0], first)
                {
                    return Err("holes_overlap".into());
                }
            }
        }
    }
    for (i, first) in polygons.iter().enumerate() {
        for second in polygons.iter().skip(i + 1) {
            let boundary_cross = first
                .iter()
                .flat_map(|a| second.iter().map(move |b| (a, b)))
                .any(|(a, b)| rings_intersect(a, b));
            let first_inside = inside(first[0][0], &second[0]);
            let second_inside = inside(second[0][0], &first[0]);
            if boundary_cross {
                return Err("polygons_overlap_edges".into());
            }
            if first_inside || second_inside {
                return Err("polygons_overlap".into());
            }
        }
    }
    Ok(())
}
fn ring_relation(ring: &Ring, container: &Ring) -> &'static str {
    if ring.iter().any(|point| on_segment(*point, container)) {
        "boundary"
    } else if ring.iter().all(|point| inside(*point, container)) {
        "inside"
    } else {
        "outside"
    }
}
fn rings_intersect(first: &Ring, second: &Ring) -> bool {
    first
        .windows(2)
        .any(|a| second.windows(2).any(|b| segments_intersect(a, b)))
}
fn segments_intersect(first: &[Point], second: &[Point]) -> bool {
    let (a, b) = (first[0], first[1]);
    let (c, d) = (second[0], second[1]);
    let orientation =
        |p: Point, q: Point, r: Point| (q.0 - p.0) * (r.1 - p.1) - (q.1 - p.1) * (r.0 - p.0);
    let values = [
        orientation(a, b, c),
        orientation(a, b, d),
        orientation(c, d, a),
        orientation(c, d, b),
    ];
    if (values[0] > 1e-12 && values[1] > 1e-12)
        || (values[0] < -1e-12 && values[1] < -1e-12)
        || (values[2] > 1e-12 && values[3] > 1e-12)
        || (values[2] < -1e-12 && values[3] < -1e-12)
    {
        return false;
    }
    on_segment(c, &[a, b])
        || on_segment(d, &[a, b])
        || on_segment(a, &[c, d])
        || on_segment(b, &[c, d])
}
fn on_segment(point: Point, ring: &[Point]) -> bool {
    ring.windows(2).any(|pair| {
        let cross = (point.0 - pair[0].0) * (pair[1].1 - pair[0].1)
            - (point.1 - pair[0].1) * (pair[1].0 - pair[0].0);
        cross.abs() < 1e-10
            && point.0 >= pair[0].0.min(pair[1].0) - 1e-10
            && point.0 <= pair[0].0.max(pair[1].0) + 1e-10
            && point.1 >= pair[0].1.min(pair[1].1) - 1e-10
            && point.1 <= pair[0].1.max(pair[1].1) + 1e-10
    })
}
fn inside(point: Point, ring: &[Point]) -> bool {
    let mut result = false;
    for pair in ring.windows(2) {
        if (pair[0].1 > point.1) != (pair[1].1 > point.1)
            && point.0
                < (pair[1].0 - pair[0].0) * (point.1 - pair[0].1) / (pair[1].1 - pair[0].1)
                    + pair[0].0
        {
            result = !result;
        }
    }
    result
}
fn inside_polygon(point: Point, polygon: &Polygon) -> bool {
    inside(point, &polygon[0]) && !polygon.iter().skip(1).any(|hole| inside(point, hole))
}

pub fn lookup_snapshot(
    snapshot: &FireBanSnapshot,
    coordinates: Coordinates,
    now: DateTime<FixedOffset>,
    max_age_days: i64,
) -> FireBanResult {
    if !coordinates.is_valid() {
        return unknown_snapshot(snapshot, "missing", "invalid_coordinates", "invalid");
    }
    let freshness = freshness(&snapshot.snapshot_created_at, now, max_age_days);
    if freshness != "fresh" {
        return unknown_snapshot(
            snapshot,
            &freshness,
            if freshness == "stale" {
                "stale_snapshot"
            } else {
                "invalid_snapshot_time"
            },
            "invalid",
        );
    }
    if let Some(reason) = validate_snapshot_shape(snapshot, now) {
        return unknown_snapshot(snapshot, "fresh", &reason, "invalid");
    }
    let mut matches = Vec::new();
    for park in &snapshot.parks {
        let boundary = match point_in_wkt(
            coordinates.latitude,
            coordinates.longitude,
            &park.geometry_wkt,
        ) {
            Ok(value) => value,
            Err(_) => {
                return unknown_snapshot(snapshot, "fresh", "invalid_snapshot_geometry", "invalid")
            }
        };
        if boundary == "inside" || boundary == "boundary" {
            matches.push((park, boundary));
        }
    }
    if matches.iter().any(|(_, boundary)| *boundary == "boundary") {
        return unknown_snapshot(snapshot, "fresh", "unresolved_boundary", "boundary");
    }
    if matches.len() != 1 {
        return unknown_snapshot(
            snapshot,
            "fresh",
            if matches.is_empty() {
                "park_not_found"
            } else {
                "conflicting_geometry"
            },
            if matches.is_empty() {
                "outside"
            } else {
                "boundary"
            },
        );
    }
    let (park, boundary) = matches[0];
    let rows: Vec<_> = snapshot
        .statuses
        .iter()
        .filter(|status| status.park_id == park.park_id)
        .collect();
    if rows.len() > 1 {
        return unknown_snapshot(snapshot, "fresh", "conflicting_status_sources", boundary);
    }
    let status = rows.first().copied();
    let normalized = status
        .map(|row| row.normalized_status.as_str())
        .unwrap_or("no_current_fire_ban_record");
    if !matches!(normalized, "active" | "no_current_fire_ban_record") {
        return unknown_snapshot(snapshot, "fresh", "unsupported_status", boundary);
    }
    FireBanResult {
        park_name: Some(park.park_name.clone()),
        jurisdiction: "Ontario Parks".into(),
        status: if normalized == "active" {
            "fire_ban"
        } else {
            "no_current_fire_ban_record"
        }
        .into(),
        source_as_of: status.map(|row| row.source_as_of.clone()),
        retrieved_at: status
            .map(|row| row.retrieved_at.clone())
            .or_else(|| Some(snapshot.snapshot_created_at.clone())),
        source_url: Some(
            status
                .map(|row| row.source_url.clone())
                .unwrap_or_else(|| "https://www.ontarioparks.ca/alerts".into()),
        ),
        source_hash: status.map(|row| row.source_hash.clone()),
        snapshot_id: Some(snapshot.snapshot_id.clone()),
        freshness,
        boundary: boundary.into(),
        uncertainty: None,
    }
}

fn validate_snapshot_shape(
    snapshot: &FireBanSnapshot,
    now: DateTime<FixedOffset>,
) -> Option<String> {
    let park_ids: HashSet<_> = snapshot
        .parks
        .iter()
        .map(|park| park.park_id.as_str())
        .collect();
    for park in &snapshot.parks {
        if park.park_id.is_empty()
            || park.park_name.is_empty()
            || park.geometry_wkt.is_empty()
            || park.source_name.is_empty()
            || park.source_url.is_empty()
            || park.source_record_id.is_empty()
            || park.source_hash.is_empty()
        {
            return Some("missing_geometry_provenance".into());
        }
        if parse_wkt(&park.geometry_wkt).is_err() {
            return Some("invalid_snapshot_geometry".into());
        }
    }
    for status in &snapshot.statuses {
        if status.source_name.is_empty()
            || status.source_url.is_empty()
            || status.source_record_id.is_empty()
            || status.source_hash.is_empty()
            || status.park_id.is_empty()
            || status.snapshot_id.is_empty()
            || status.normalized_status.is_empty()
            || status.raw_wording.is_empty()
            || status.source_as_of.is_empty()
            || status.retrieved_at.is_empty()
            || !park_ids.contains(status.park_id.as_str())
            || status.source_name != "Ontario Parks"
            || status.snapshot_id != snapshot.snapshot_id
        {
            return Some("missing_status_provenance".into());
        }
        if !valid_status_time(&status.source_as_of, now, true)
            || !valid_status_time(&status.retrieved_at, now, false)
        {
            return Some("invalid_status_time".into());
        }
    }
    None
}
fn freshness(value: &str, now: DateTime<FixedOffset>, max_age_days: i64) -> String {
    if max_age_days < 0 {
        return "missing".into();
    }
    let Ok(created) = DateTime::parse_from_rfc3339(value) else {
        return "missing".into();
    };
    if created > now {
        return "missing".into();
    }
    if (now - created).num_seconds() <= max_age_days * 86400 {
        "fresh".into()
    } else {
        "stale".into()
    }
}
fn valid_status_time(value: &str, now: DateTime<FixedOffset>, allow_date: bool) -> bool {
    if allow_date && value.len() == 10 {
        return NaiveDate::parse_from_str(value, "%Y-%m-%d")
            .map(|date| date <= now.date_naive())
            .unwrap_or(false);
    }
    DateTime::parse_from_rfc3339(value)
        .map(|date| date <= now)
        .unwrap_or(false)
}
fn unknown_snapshot(
    snapshot: &FireBanSnapshot,
    freshness: &str,
    reason: &str,
    boundary: &str,
) -> FireBanResult {
    FireBanResult {
        park_name: None,
        jurisdiction: "Ontario Parks".into(),
        status: "unknown".into(),
        source_as_of: None,
        retrieved_at: Some(snapshot.snapshot_created_at.clone()),
        source_url: Some("https://www.ontarioparks.ca/alerts".into()),
        source_hash: None,
        snapshot_id: Some(snapshot.snapshot_id.clone()),
        freshness: freshness.into(),
        boundary: boundary.into(),
        uncertainty: Some(reason.into()),
    }
}
