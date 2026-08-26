use log::debug;
use rodio::{source::SineWave, OutputStream, Sink, Source};
use std::time::Duration;

#[derive(Clone, Copy)]
pub enum Cue {
    Start,
    End,
    Error,
}

pub fn play(cue: Cue) {
    if !crate::APP_STATE.config.read().core.asr.sound_notification {
        return;
    }

    std::thread::spawn(move || {
        if let Err(error) = play_sync(cue) {
            debug!("Sound notification unavailable: {}", error);
        }
    });
}

fn play_sync(cue: Cue) -> Result<(), String> {
    let (_stream, handle) = OutputStream::try_default().map_err(|error| error.to_string())?;
    let sink = Sink::try_new(&handle).map_err(|error| error.to_string())?;

    match cue {
        Cue::Start => append_tone(&sink, 1000.0, 80, 0.18),
        Cue::End => append_tone(&sink, 600.0, 100, 0.18),
        Cue::Error => {
            append_tone(&sink, 400.0, 80, 0.2);
            sink.append(
                rodio::source::Zero::<f32>::new(1, 44_100).take_duration(Duration::from_millis(50)),
            );
            append_tone(&sink, 400.0, 80, 0.2);
        }
    }

    sink.sleep_until_end();
    Ok(())
}

fn append_tone(sink: &Sink, frequency: f32, duration_ms: u64, volume: f32) {
    sink.append(
        SineWave::new(frequency)
            .take_duration(Duration::from_millis(duration_ms))
            .amplify(volume),
    );
}
