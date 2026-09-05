use crate::models::MAX_SMS_SEPTETS;

const GSM_BASIC: &str = "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ !\"#¤%&'()*+,-./0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§abcdefghijklmnopqrstuvwxyzäöñüà";
const GSM_EXTENDED: &str = "^{}\\[~]|";

fn replacement(character: char) -> Option<&'static str> {
    Some(match character {
        '’' | '‘' => "'",
        '“' | '”' => "\"",
        '–' | '—' => "-",
        '…' => "...",
        '•' => "-",
        '°' => " ",
        '\u{00a0}' => " ",
        _ => return None,
    })
}

fn is_supported(character: char) -> bool {
    GSM_BASIC.contains(character) || GSM_EXTENDED.contains(character)
}

pub fn septet_count(text: &str) -> usize {
    text.chars()
        .map(|character| usize::from(GSM_EXTENDED.contains(character)) + 1)
        .sum()
}

pub fn normalize(text: &str) -> String {
    let mut value = String::new();
    for character in text.chars() {
        if let Some(mapped) = replacement(character) {
            value.push_str(mapped);
        } else if is_supported(character) {
            value.push(character);
        } else {
            value.push('?');
        }
    }
    value.split_whitespace().collect::<Vec<_>>().join(" ")
}

pub fn bound_sms(text: &str, fallback: &str) -> String {
    let safe = normalize(text);
    let candidate = if safe.is_empty() {
        normalize(fallback)
    } else {
        safe
    };
    let bounded = truncate(&candidate);
    if bounded.is_empty() {
        return truncate(&normalize(fallback));
    }
    bounded.trim_end().to_owned()
}

fn truncate(candidate: &str) -> String {
    let mut output = String::new();
    let mut septets = 0;
    for character in candidate.chars() {
        let cost = usize::from(GSM_EXTENDED.contains(character)) + 1;
        if septets + cost > MAX_SMS_SEPTETS {
            break;
        }
        output.push(character);
        septets += cost;
    }
    output
}
