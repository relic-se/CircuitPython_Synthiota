# SPDX-FileCopyrightText: Copyright (c) 2026 Cooper Dalrymple
#
# SPDX-License-Identifier: Unlicense
import time

import relic_synthiota

DELAY = 0.1
COLOR = 0xFF00FF

synthiota = relic_synthiota.Synthiota()

while True:
    for i in range(16):
        synthiota.step_leds = [COLOR if i == j else 0x000000 for j in range(16)]
        time.sleep(DELAY)
        synthiota.step_leds = 0x000000

    for i in range(8):
        synthiota.pot_leds = [COLOR if i == j else 0x000000 for j in range(8)]
        time.sleep(DELAY)
        synthiota.pot_leds = 0x000000

    for i in range(3):
        synthiota.left_slider_leds = [COLOR if i == j else 0x000000 for j in range(3)]
        time.sleep(DELAY)
        synthiota.left_slider_leds = 0x000000

    synthiota.up_led = COLOR
    time.sleep(DELAY)
    synthiota.up_led = 0x000000

    synthiota.down_led = COLOR
    time.sleep(DELAY)
    synthiota.down_led = 0x000000

    for i in range(3):
        synthiota.right_slider_leds = [COLOR if i == j else 0x000000 for j in range(3)]
        time.sleep(DELAY)
        synthiota.right_slider_leds = 0x000000

    for i in range(3):
        synthiota.mode_leds = [COLOR if i == j else 0x000000 for j in range(3)]
        time.sleep(DELAY)
        synthiota.mode_leds = 0x000000

    synthiota.edit_led = COLOR
    time.sleep(DELAY)
    synthiota.edit_led = 0x000000

    synthiota.mode_led = COLOR
    time.sleep(DELAY)
    synthiota.mode_led = 0x000000

    synthiota.play_led = COLOR
    time.sleep(DELAY)
    synthiota.play_led = 0x000000
