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

* 1 x `Synthiota PCB <https://github.com/todbot/synthiota/>`_
* 1 x `Raspberry Pi Pico 2 <https://www.adafruit.com/product/6006>`_
* 1 x `PCM5102 I2S Stereo DAC <https://amzn.to/4nX4xkD>`_
* 1 x `SH1106 128x64 1.3" SPI OLED <https://amzn.to/4nX4xkD>`_
* 2 x `PJ320A 3.5mm stereo jack <https://amzn.to/4i5F33d>`_
* 8 x `RK09K 10k vertical potentiometer <https://amzn.to/47XbwEk>`_
* 1 x `EC11 rotary encoder <https://amzn.to/4o1vSSW>`_

**Software and Dependencies:**

* Adafruit CircuitPython firmware for the supported boards:
  https://circuitpython.org/downloads
* todbot's TMIDI library: https://github.com/todbot/CircuitPython_TMIDI
* Adafruit's Debouncer library: https://github.com/adafruit/Adafruit_CircuitPython_Debouncer
* Adafruit's DisplayIO SH1106 library: https://github.com/adafruit/Adafruit_CircuitPython_DisplayIO_SH1106
* Adafruit's MPR121 library: https://github.com/adafruit/Adafruit_CircuitPython_MPR121
* Adafruit's NeoPixel library: https://github.com/adafruit/Adafruit_CircuitPython_NeoPixel
"""

import array
import time

import adafruit_debouncer
import adafruit_displayio_sh1106
import adafruit_mpr121
import analogio
import audiobusio
import audiomixer
import board
import busio
import digitalio
import displayio
import fourwire
import neopixel
import rotaryio
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

_MPR121_POLLING = 0.01

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


class Slider:
    """Simple capacitive touch slider made from three pads attached to an MPR121."""

    def __init__(self, pads: list, wrap: bool = False, offset: int = 0, scale: int = None):
        """Create a Slider object using the provided MPR121 channels.

        :param pads: A list of 3 adafruit_mpr121.MPR121_Channel objects
        :param wrap: Whether or not to wrap the value in a "circular" fashion
        :param offset: An offset that will be applied to the slider value from 0 to 1
        :param scale: The size of each pad, defaults to 0.333.
        """
        if len(pads) != 3:
            raise ValueError("Invalid number of pads")

        self._channels = tuple(pads)
        self._wrap = wrap
        self._offset = offset
        self._scale = scale if scale is not None else 1 / len(self._channels)
        self._value = 0

    @property
    def value(self) -> float:
        """Get the position of the slider as a number from 0 to 1 or returns `None` if there is no
        touch detected.
        """
        a, b, c = ((x.raw_value - x.threshold) / x.threshold for x in self._channels)

        value = None

        # cases when finger is touching two pads
        if a >= 0 and b >= 0:
            value = self._scale * (0 + (b / (a + b)))
        elif b >= 0 and c >= 0:
            value = self._scale * (1 + (c / (b + c)))
        elif c >= 0 and a >= 0 and self._wrap:
            value = self._scale * (2 + (a / (c + a)))

        # special cases when finger is just on a single pad
        elif a > 0 and b <= 0 and c <= 0:
            value = 0 * self._scale
        elif a <= 0 and b > 0 and c <= 0:
            value = 1 * self._scale
        elif a <= 0 and b <= 0 and c > 0 and self._wrap:
            value = 2 * self._scale

        if value is not None:  # i.e. if touched
            # filter noise
            if abs(value - self._value) > 0.5:
                value = self._value
            else:
                self._value = value

            # apply offset
            value = (value + self._offset) % 1
        return value


class Synthiota:
    """Helper library for Synthiota."""

    def __init__(
        self,
        voice_count: int = 1,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        channel_count: int = DEFAULT_CHANNEL_COUNT,
        buffer_size: int = 4096,
    ):
        """Setup hardware resources including audio output, midi usb/uart, touch inputs, display,
        neopixels, encoder, and potentiometers.

        :param voice_count: The maximum number of voices to mix
        :param sample_rate: The sample rate to be used for all samples
        :type sample_rate: int
        :param channel_count: The number of channels the source samples contain. 1 = mono; 2 =
            stereo.
        :type channel_count: int
        :param buffer_size: The total size in bytes of the buffers to mix into
        :type buffer_size: int
        """

        # audio
        self._voice_count = voice_count
        self._sample_rate = sample_rate
        self._channel_count = channel_count
        self._buffer_size = buffer_size
        self._audio = audiobusio.I2SOut(
            bit_clock=I2S_BCLK_PIN,
            word_select=I2S_LRCLK_PIN,
            data=I2S_DATA_PIN,
        )
        self._mixer = audiomixer.Mixer(
            voice_count=voice_count,
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
        self._mpr121_touched = [False] * (len(MPR121_I2C_ADDRS) * 12)
        self._mpr121_timestamp = 0

        self._octave_up_button = adafruit_debouncer.Button(
            lambda: self._update_touched() or self._mpr121_touched[PAD_OCTAVE_UP],
            value_when_pressed=True,
        )
        self._octave_down_button = adafruit_debouncer.Button(
            lambda: self._update_touched() or self._mpr121_touched[PAD_OCTAVE_DOWN],
            value_when_pressed=True,
        )

        self._left_slider = Slider(
            [
                adafruit_mpr121.MPR121_Channel(self._mpr121[i // 12], i % 12)
                for i in (PAD_LSLIDE_A, PAD_LSLIDE_B, PAD_LSLIDE_C)
            ]
        )
        self._right_slider = Slider(
            [
                adafruit_mpr121.MPR121_Channel(self._mpr121[i // 12], i % 12)
                for i in (PAD_RSLIDE_A, PAD_RSLIDE_B, PAD_RSLIDE_C)
            ]
        )

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
        self._encoder_switch = digitalio.DigitalInOut(ENCODER_SW_PIN)
        self._encoder_switch.switch_to_input(pull=True)
        self._encoder_button = adafruit_debouncer.Button(
            self._encoder_switch, value_when_pressed=False
        )

        # pots
        self._adc = analogio.AnalogIn(ADC_PIN)
        self._adc_raw_value = array.array("H", [0] * ADC_COUNT)
        self._adc_value = [0] * ADC_COUNT
        self._adc_mux_pins = tuple([digitalio.DigitalInOut(pin) for pin in ADC_MUX_PINS])
        for dio in self._adc_mux_pins:
            dio.switch_to_output(value=False)

    @property
    def voice_count(self) -> int:
        """The maximum number of voices available in the mixer"""
        return self._voice_count

    @property
    def sample_rate(self) -> int:
        """How quickly samples are played through the audio output in Hertz (cycles per second)"""
        return self._sample_rate

    @property
    def channel_count(self) -> int:
        """The number of channels of the audio output. 1 = mono; 2 = stereo."""
        return self._channel_count

    @property
    def buffer_size(self) -> int:
        """The total size in bytes of the buffers used by the mixer"""
        return self._buffer_size

    @property
    def audio(self) -> audiobusio.I2SOut:
        """The I2S audio output object."""
        return self._audio

    @property
    def mixer(self) -> audiomixer.Mixer:
        """The audio output mixer. Use this object to attach your audio sources."""
        return self._mixer

    @property
    def display(self) -> adafruit_displayio_sh1106.SH1106:
        """The display bus object."""
        return self._display

    @property
    def leds(self) -> neopixel.NeoPixel:
        """The neopixel driver which controls all 27 leds on the device."""
        return self._leds

    @property
    def encoder_position(self) -> int:
        """The current position of the encoder in terms of pulses. The number of pulses per rotation
        is defined by the specific hardware and by the divisor.
        """
        return self._encoder.position

    @property
    def encoder_button(self) -> adafruit_debouncer.Button:
        """The object for the encoder button."""
        return self._encoder_button

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

    def _update_touched(self) -> None:
        if (now := time.monotonic()) - self._mpr121_timestamp >= _MPR121_POLLING:
            self._mpr121_timestamp = now
            for i, x in enumerate(self._mpr121):
                for j, v in enumerate(x.touched_pins):
                    self._mpr121_touched[i * 12 + j] = v

    @property
    def touched(self) -> tuple:
        """The state of all touchpads as a tuple of 24 booleans."""
        self._update_touched()
        return tuple(self._mpr121_touched)

    @property
    def touched_steps(self) -> tuple:
        """The state of all 16 step touch pads in order left-to-right from bottom-left to
        top-right.
        """
        self._update_touched()
        return tuple([self._mpr121_touched[i] for i in STEP_PADS])

    @property
    def octave_up_button(self) -> adafruit_debouncer.Button:
        """The object for the octave up button."""
        return self._octave_up_button

    @property
    def octave_down_button(self) -> adafruit_debouncer.Button:
        """The object for the octave down button."""
        return self._octave_down_button

    @property
    def left_slider(self) -> Slider:
        """The object for the left horizontal touch slider."""
        return self._left_slider

    @property
    def right_slider(self) -> Slider:
        """The object for the right horizontal touch slider."""
        return self._right_slider

    def get_midi_messages(self) -> tuple:
        """Read all available messages from both the USB and UART MIDI ports."""
        msgs = []
        while msg := self._midi_usb.receive() or self._midi_uart.receive():
            msgs.append(msg)
        return tuple(msgs)

    def send_midi_message(self, message: tmidi.Message) -> None:
        """Send a message to both the USB and UART MIDI ports.

        :param message: The MIDI message you would like to send.
        """
        self._midi_usb.send(message)
        self._midi_uart.send(message)
