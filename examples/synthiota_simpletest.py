# SPDX-FileCopyrightText: 2017 Scott Shawcroft, written for Adafruit Industries
# SPDX-FileCopyrightText: Copyright (c) 2026 Cooper Dalrymple
#
# SPDX-License-Identifier: Unlicense
import random
import time

import displayio
import synthio
import tmidi
import vectorio

import relic_synthiota

displayio.release_displays()
synthiota = relic_synthiota.Synthiota()

# display
root_group = displayio.Group()
synthiota.display.root_group = root_group

palette = displayio.Palette(1)
palette[0] = 0xFFFFFF
root_group.append(
    vectorio.Circle(
        pixel_shader=palette,
        radius=synthiota.display.width // 2,
        x=synthiota.display.width // 2,
        y=synthiota.display.height // 2,
    )
)

# audio
synth = synthio.Synthesizer(synthiota.sample_rate)
synth.envelope = synthio.Envelope(attack_time=0.05, attack_level=0.8, release_time=0.6)
synthiota.mixer.voice[0].play(synth)
synthiota.mixer.voice[0].level = 0.25  # 0.25 usually better for headphones, 1.0 for line-in

notenum = None
note_counter = 0
last_timestamp = time.monotonic()
while True:
    current_timestamp = time.monotonic()
    delta = current_timestamp - last_timestamp

    # synth
    if (note_counter := note_counter - delta) <= 0:
        if notenum is None:
            notenum = random.randint(32, 60)
            synth.press(notenum)
            synthiota.send_midi_message(tmidi.Message(tmidi.NOTE_ON, data0=notenum, data1=127))
            note_counter = 0.3
        else:
            synth.release(notenum)
            synthiota.send_midi_message(tmidi.Message(tmidi.NOTE_OFF, data0=notenum))
            notenum = None
            note_counter = 0.5

    # controls
    print("Encoder Position:", synthiota.encoder_position)
    print("Encoder Switch:", synthiota.encoder_button.value)
    print("Octave Up:", synthiota.octave_up_button.value)
    print("Octave Down:", synthiota.octave_up_button.value)
    print("Left Slider:", synthiota.left_slider.value)
    print("Right Slider:", synthiota.right_slider.value)
    print("Steps:", "".join([str(int(x)) for x in synthiota.touched_steps]))

    time.sleep(0.1)
