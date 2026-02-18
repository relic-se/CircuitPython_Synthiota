# SPDX-FileCopyrightText: 2017 Scott Shawcroft, written for Adafruit Industries
# SPDX-FileCopyrightText: Copyright (c) 2026 Cooper Dalrymple (@relic-se)
# SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt (@todbot)
#
# SPDX-License-Identifier: MIT
"""
`synthiota`
================================================================================

Helper library for Synthiota


* Author(s): Cooper Dalrymple

Implementation Notes
--------------------

**Hardware:**

.. todo:: Add links to any specific hardware product page(s), or category page(s).
  Use unordered list & hyperlink rST inline format: "* `Link Text <url>`_"

**Software and Dependencies:**

* Adafruit CircuitPython firmware for the supported boards:
  https://circuitpython.org/downloads

.. todo:: Uncomment or remove the Bus Device and/or the Register library dependencies
  based on the library's use of either.

# * Adafruit's Bus Device library: https://github.com/adafruit/Adafruit_CircuitPython_BusDevice
# * Adafruit's Register library: https://github.com/adafruit/Adafruit_CircuitPython_Register
"""

import adafruit_displayio_sh1106
import adafruit_mpr121
import analogio
import array
import audiobusio
import audiomixer
import board
import busio
import digitalio
import displayio
import fourwire
import keypad
import neopixel
import rotaryio
import time
import tmidi
import usb_midi
from micropython import const

__version__ = "0.0.0+auto.0"
__repo__ = "https://github.com/relic-se/CircuitPython_Synthiota.git"

# pin mapping

LED_PIN = board.GP18
LED_COUNT = const(27)
LED_BRIGHTNESS = 0.1

I2C_SDA_PIN = board.GP2
I2C_SCL_PIN = board.GP3

DISPLAY_SCLK_PIN = board.GP10
DISPLAY_MOSI_PIN = board.GP11
DISPLAY_RESET_PIN = board.GP12
DISPLAY_DC_PIN = board.GP13

ADC_MUX_PINS = (board.GP9, board.GP8, board.GP7)
ADC_PIN = board.GP26
ADC_COUNT = const(8)

ENCODER_A_PIN = board.GP27
ENCODER_B_PIN = board.GP28
ENCODER_SW_PIN = board.GP19

UART_RX_PIN = board.GP17
UART_TX_PIN = board.GP16

I2S_BCLK_PIN = board.GP20
I2S_LRCLK_PIN = board.GP21
I2S_DATA_PIN = board.GP22

MPR121_I2C_ADDRS = (0x5A, 0x5B)

# program constants

DEFAULT_SAMPLE_RATE = const(44100)
DEFAULT_CHANNEL_COUNT = const(2)
DEFAULT_BUFFER_SIZE = const(4096)

DISPLAY_WIDTH = const(132)
DISPLAY_HEIGHT = const(64)

_ENCODER_SW_POLLING = 0.05

# map touch id to led index
PAD_TO_LED = (7, 6, 5, 4, 3, 2, 1, 0, 8, 9, 10, 11, 18, 17, 16, 15, 23, 22, 21, 20, 19, 12, 13, 14)

# map step pads to an index
STEP_PADS = (7, 6, 5, 4, 3, 2, 1, 0, 8, 9, 10, 11, 18, 17, 16, 15)

# pad defs
PAD_OCTAVE_DOWN = const(19)
PAD_OCTAVE_UP = const(20)
PAD_RSLIDE_C = const(14)
PAD_RSLIDE_B = const(13)
PAD_RSLIDE_A = const(12)
PAD_LSLIDE_C = const(23)
PAD_LSLIDE_B = const(22)
PAD_LSLIDE_A = const(21)


class Synthioa:
    def __init__(
        self,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        channel_count: int = DEFAULT_CHANNEL_COUNT,
        buffer_size: int = 4096,
    ):
        # audio
        self._audio = audiobusio.I2SOut(
            bit_clock=I2S_BCLK_PIN,
            word_select=I2S_LRCLK_PIN,
            data=I2S_DATA_PIN,
        )
        self._mixer = audiomixer.Mixer(
            sample_rate=sample_rate,
            channel_count=channel_count,
            buffer_size=buffer_size,
        )
        self._audio.play(self._mixer)

        # midi
        self._uart = busio.UART(
            rx=UART_RX_PIN,
            tx=UART_TX_PIN,
            baudrate=31250,
            timeout=0.001,
        )
        self._midi_uart = tmidi.MIDI(
            midi_in=self._uart,
            midi_out=self._uart,
        )
        self._midi_usb = tmidi.MIDI(
            midi_in=usb_midi.ports[0],
            midi_out=usb_midi.ports[1],
        )

        # touch
        self._i2c = busio.I2C(
            scl=I2C_SCL_PIN,
            sda=I2C_SDA_PIN,
            frequency=400_000,
        )
        self._mpr121 = tuple(
            [adafruit_mpr121.MPR121(self._i2c, address=a) for a in MPR121_I2C_ADDRS]
        )
        self._mpr121[1]._write_register_byte(adafruit_mpr121.MPR121_CONFIG1, 0x10)

        # display
        displayio.release_displays()
        self._spi = busio.SPI(
            clock=DISPLAY_SCLK_PIN,
            MOSI=DISPLAY_MOSI_PIN,
        )
        self._display_bus = fourwire.FourWire(
            self._spi,
            command=DISPLAY_DC_PIN,
            reset=DISPLAY_RESET_PIN,
            baudrate=24_000_000,
        )
        self._display = adafruit_displayio_sh1106.SH1106(
            self._display_bus,
            width=DISPLAY_WIDTH,
            height=DISPLAY_HEIGHT,
            colstart=3,
        )

        # leds
        self._leds = neopixel.NeoPixel(LED_PIN, LED_COUNT, brightness=LED_BRIGHTNESS)
        self._leds.fill(0x000000)

        # encoder
        self._encoder = rotaryio.IncrementalEncoder(
            pin_a=ENCODER_A_PIN,
            pin_b=ENCODER_B_PIN,
            divisor=4,
        )
        self._encoder_sw = keypad.Keys(
            (ENCODER_SW_PIN,),
            value_when_pressed=False,
            pull=True,
        )
        self._encoder_sw_timestamp = 0
        self._encoder_sw_event = keypad.Event(0, False)
        self._encoder_sw_pressed = False

        # pots
        self._adc = analogio.AnalogIn(ADC_PIN)
        self._adc_raw_value = array.array('H', [0] * ADC_COUNT)
        self._adc_value = [0] * ADC_COUNT
        self._adc_mux_pins = tuple([digitalio.DigitalInOut(pin) for pin in ADC_MUX_PINS])
        for dio in self._adc_mux_pins:
            dio.switch_to_output(value=False)

    @property
    def audio(self) -> audiobusio.I2SOut:
        return self._audio

    @property
    def mixer(self) -> audiomixer.Mixer:
        return self._mixer

    @property
    def display(self) -> adafruit_displayio_sh1106.SH1106:
        return self._display

    @property
    def leds(self) -> neopixel.NeoPixel:
        return self._leds

    @property
    def encoder_position(self) -> int:
        return self._encoder.position
    
    def _update_encoder_sw(self) -> None:
        if (now := time.monotonic()) - self._encoder_sw_timestamp >= _ENCODER_SW_POLLING:
            self._encoder_sw_timestamp = now
            while self._encoder_sw.events.get_into(self._encoder_sw_event):
                if self._encoder_sw_event.pressed:
                    self._encoder_sw_pressed = True
                elif self._encoder_sw_event.released:
                    self._encoder_sw_pressed = False

    @property
    def encoder_pressed(self) -> bool:
        self._update_encoder_sw()
        return self._encoder_sw_pressed
    
    @property
    def encoder_just_pressed(self) -> bool:
        self._update_encoder_sw()
        return self._encoder_sw_event.pressed
    
    @property
    def encoder_just_released(self) -> bool:
        self._update_encoder_sw()
        return self._encoder_sw_event.released

    def _adc_mux_select(self, index: int) -> None:
        for i, dio in enumerate(self._adc_mux_pins):
            dio.value = bool(index & (1 << i))

    def _get_adc_value(self, index: int) -> int:
        self._adc_mux_select(index)
        return self._adc.value

    def _update_adc_values(self) -> None:
        for i in range(ADC_COUNT):
            self._adc_raw_value[i] = self._get_adc_value(i)
            self._adc_value[i] = self._adc_raw_value[i] / 65535

    def get_touched(self) -> int:
        return sum([x.touched_pins for x in self._mpr121], ())

    def get_midi_messages(self) -> list:
        msgs = []
        while msg := self._midi_usb.receive() or self._midi_uart.receive():
            msgs.append(msg)

    def send_midi_message(self, message: tmidi.Message) -> None:
        self._midi_usb.send(message)
        self._midi_uart.send(message)
