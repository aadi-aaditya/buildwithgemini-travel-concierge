import asyncio
import base64
import os
import shutil
import struct
import math
import numpy as np
from scipy.io import wavfile
from playwright.async_api import async_playwright
from moviepy import VideoFileClip, AudioFileClip, CompositeAudioClip

ARTIFACT_DIR = "/config/.gemini/antigravity/brain/de95c9e8-1988-4e79-b44d-3934b1100b28"
OUTPUT_MP4 = os.path.join(ARTIFACT_DIR, "travel_concierge_demo.mp4")
LOCAL_MP4 = "/config/Desktop/Session1/travel-concierge/travel_concierge_demo.mp4"

def generate_lofi_music(duration_sec=30, sample_rate=44100):
    """Generates an upbeat lo-fi chill hop track with chord progression, soft beat, and vinyl warmth."""
    num_samples = int(duration_sec * sample_rate)
    t = np.linspace(0, duration_sec, num_samples, endpoint=False)
    
    # 1. Warm Lo-Fi Chord Progression: Cmaj7 -> Am7 -> Dm7 -> G7 (bpm = 85)
    bpm = 85
    beat_dur = 60.0 / bpm
    bar_dur = beat_dur * 4
    
    # Frequencies for chords (Hz)
    chords = [
        [261.63, 329.63, 392.00, 493.88], # Cmaj7
        [220.00, 261.63, 329.63, 392.00], # Am7
        [293.66, 349.23, 440.00, 523.25], # Dm7
        [196.00, 246.94, 293.66, 349.23], # G7
    ]
    
    music = np.zeros(num_samples)
    
    for i in range(num_samples):
        sec = t[i]
        bar_idx = int(sec / bar_dur) % len(chords)
        current_chord = chords[bar_idx]
        
        # Soft sine synth with warm harmonics
        val = 0.0
        for freq in current_chord:
            val += 0.12 * math.sin(2 * math.pi * freq * sec)
            val += 0.04 * math.sin(2 * math.pi * (freq * 2) * sec) # subtle octave harmonic
        
        # Envelope to soften chord transitions
        phase_in_bar = (sec % bar_dur) / bar_dur
        env = math.sin(math.pi * phase_in_bar) ** 0.5
        music[i] += val * env
    
    # 2. Add Kick and Snare Lo-Fi Beat
    beat_samples = int(beat_dur * sample_rate)
    kick = np.sin(2 * math.pi * np.linspace(120, 40, int(0.12 * sample_rate)) * np.linspace(0, 0.12, int(0.12 * sample_rate))) * np.exp(-15 * np.linspace(0, 0.12, int(0.12 * sample_rate)))
    snare_noise = np.random.normal(0, 0.1, int(0.15 * sample_rate)) * np.exp(-20 * np.linspace(0, 0.15, int(0.15 * sample_rate)))
    
    beat_track = np.zeros(num_samples)
    for b in range(int(duration_sec / beat_dur)):
        idx = int(b * beat_samples)
        beat_in_bar = b % 4
        if beat_in_bar in [0, 2]: # Kick on 1 and 3
            end_idx = min(idx + len(kick), num_samples)
            beat_track[idx:end_idx] += kick[:end_idx-idx] * 0.45
        if beat_in_bar in [1, 3]: # Snare on 2 and 4
            end_idx = min(idx + len(snare_noise), num_samples)
            beat_track[idx:end_idx] += snare_noise[:end_idx-idx] * 0.25

    # 3. Subtle Vinyl Crackle
    crackle = np.random.choice([0, 0.02, -0.02], size=num_samples, p=[0.992, 0.004, 0.004])

    final_audio = music * 0.5 + beat_track * 0.5 + crackle * 0.2
    # Normalize to 16-bit PCM
    final_audio = np.clip(final_audio, -1.0, 1.0)
    audio_int16 = (final_audio * 32767).astype(np.int16)
    
    wav_path = "lofi_music.wav"
    wavfile.write(wav_path, sample_rate, audio_int16)
    return wav_path


async def record():
    print("Starting Playwright demo recording...")
    temp_dir = "temp_video_record"
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            record_video_dir=temp_dir,
            record_video_size={"width": 1280, "height": 720}
        )
        page = await context.new_page()

        print("Navigating to http://localhost:8080...")
        await page.goto("http://localhost:8080")
        await page.wait_for_timeout(2000)

        # 1. Ask first prompt: What the app does best (Recommendations & Attractions)
        print("Sending prompt 1...")
        prompt1 = "Find top attractions and nearby vegan restaurants in Kyoto, Japan"
        await page.fill("#input", prompt1)
        await page.wait_for_timeout(1000)
        await page.click("button:has-text('Send')")
        
        # Wait for agent response to populate
        await page.wait_for_timeout(8000)

        # 2. Ask second prompt: Richer prompt (Postcard Image + Trip Budget)
        print("Sending prompt 2...")
        prompt2 = "Generate a travel postcard for Kyoto and calculate a 3-day budget for 2 travelers with $800"
        await page.fill("#input", prompt2)
        await page.wait_for_timeout(1000)
        await page.click("button:has-text('Send')")

        # Wait for image and budget card response
        await page.wait_for_timeout(12000)

        await page.wait_for_timeout(3000)
        
        # Close context to finish writing webm video
        video_path = await page.video.path()
        await context.close()
        await browser.close()
        print(f"Raw video recorded to: {video_path}")

        # Generate upbeat lo-fi audio track
        print("Generating lo-fi music track...")
        audio_path = generate_lofi_music(duration_sec=30)

        # Merge video and audio with moviepy
        print("Merging video and lo-fi audio with MoviePy...")
        video_clip = VideoFileClip(video_path)
        audio_clip = AudioFileClip(audio_path).subclipped(0, min(video_clip.duration, 30))
        
        final_clip = video_clip.with_audio(audio_clip)
        
        final_clip.write_videofile(
            LOCAL_MP4,
            codec="libx264",
            audio_codec="aac",
            fps=24,
            preset="fast"
        )
        
        # Copy to artifact directory for presentation
        os.makedirs(ARTIFACT_DIR, exist_ok=True)
        shutil.copy(LOCAL_MP4, OUTPUT_MP4)
        print(f"Demo video successfully created at:\n- {LOCAL_MP4}\n- {OUTPUT_MP4}")


if __name__ == "__main__":
    asyncio.run(record())
