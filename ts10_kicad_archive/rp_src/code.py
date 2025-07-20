
import board
import math
import time
import busio
from digitalio import DigitalInOut, Direction, Pull

import adafruit_mpr121
import neopixel

import usb_midi
import adafruit_midi

from adafruit_midi.note_on          import NoteOn
from adafruit_midi.note_off         import NoteOff
from adafruit_midi.control_change   import ControlChange
from adafruit_midi.pitch_bend       import PitchBend


'''
TODO

[x] Channel set
[x] MIDI Thru
[x] Organ mode
[ ] Chord mode
[x] Pluck mode
[ ] Mod/bend wheels

'''



# Set tuning options in freeplay (chromatic) mode
# bass is EADG, guitar (bottom 4 strings) is DGBE, violin is   
# CDAE, etc. OCT has each string begin one octave up from the
# next, FULL assigns each pad a unique note.
###############################################################
BASS = [19, 14,  9,  4]                                       #
GUIT = [28, 23, 19, 14]                                       #
VIOL = [40, 33, 26, 19]                                       #
OCT  = [36, 24, 12,  0]                                       #
FULL = [45, 30, 15,  0]                                       #
INS =  [BASS, GUIT, VIOL, OCT, FULL] # List of tuning options #
tune = BASS                          # Default tuning         #
###############################################################


# Set string offsets in 10string mode
###############################################################
string1 = 7  # Offset of 1st string above root string         #
string2 = 12 # Offset of 2nd string above root string         #
###############################################################

# Set scales in organ mode
###############################################################
BIMANUAL = [ # Silent keys set to 128, triggers ValueError    #
             # which is passed                                #
[13, 15,128, 18, 20, 22,128, 25, 27,128, 30, 32, 34,128, 37], #
[12, 14, 16, 17, 19, 21, 23, 24, 26, 28, 29, 31, 33, 35, 36], #
[ 1,  3,128,  6,  8, 10,128, 13, 15,128, 18, 20, 22,128, 25], #
[ 0,  2,  4,  5,  7,  9, 11, 12, 14, 16, 17, 19, 21, 23, 24]  #
]                                                             #
                                                              #
organ_tune = BIMANUAL                                         #
###############################################################


# Default transposition & MIDI stuff
###############################################################
transpose = 36                                                #
velocity = 127                                                #
midi_channel = 1                                              #
###############################################################



SET = 0        # Use the SET key to choose mode, transposition, and tuning
FREEPLAY = 1   # Tap frets to play notes
PLUCK = 2      # Hold frets & tap strings to play notes
TSTR = 3       # PLUCK but extra strings are activated & transposed 1 5th and 1 oct above
CHORD = 4
ORGAN = 5      # rows of white & black keys, like 2 organ manuals, or a computer keyboard

modes = [SET, FREEPLAY, PLUCK, TSTR, CHORD, ORGAN]

mode = FREEPLAY
prev_mode = mode
new_mode = mode



# Create hardware

i2c0 = busio.I2C(board.GP21, board.GP20)
i2c1 = busio.I2C(board.GP19, board.GP18)

pixels = neopixel.NeoPixel(board.GP23, 4)

mpr0 = adafruit_mpr121.MPR121(i2c0, address=0x5B)
mpr1 = adafruit_mpr121.MPR121(i2c0, address=0x5A)
mpr2 = adafruit_mpr121.MPR121(i2c0, address=0x5D)
mpr3 = adafruit_mpr121.MPR121(i2c0, address=0x5C)

mpr4 = adafruit_mpr121.MPR121(i2c1, address=0x5B)
mpr5 = adafruit_mpr121.MPR121(i2c1, address=0x5A)

sensors = [mpr0, mpr1, mpr2, mpr3, mpr4, mpr5]


set_pin = DigitalInOut(board.GP16)
con_pin = DigitalInOut(board.GP17)

set_pin.direction = Direction.INPUT
con_pin.direction = Direction.INPUT

set_pin.pull = Pull.UP
con_pin.pull = Pull.UP



# Create MIDI IO

uart = busio.UART(board.GP0, board.GP1, baudrate=31250, timeout=0.001)

midi = adafruit_midi.MIDI(
                            midi_out=usb_midi.ports[1],
                            out_channel=midi_channel-1,
                            midi_in = usb_midi.ports[0],
                            in_channel = midi_channel-1,
                            debug=False,
                            )

hmidi = adafruit_midi.MIDI(
                            midi_in=uart,
                            midi_out=uart,
                            in_channel=(midi_channel - 1),
                            out_channel=(midi_channel - 1),
                            debug=False,
                            )



# Pretty lights

def wheel(pos):
    # Input a value 0 to 255 to get a color value.
    # The colours are a transition r - g - b - back to r.
    if pos < 0 or pos > 255:
        r = g = b = 0
    elif pos < 85:
        r = int(pos * 3)
        g = int(255 - pos * 3)
        b = 0
    elif pos < 170:
        pos -= 85
        r = int(255 - pos * 3)
        g = 0
        b = int(pos * 3)
    else:
        pos -= 170
        r = 0
        g = int(pos * 3)
        b = int(255 - pos * 3)
    return (r, g, b)



# Mapping strings to frets & sensors & notes

F_STRUM_MAP = [0, 1, 1, 1, 2, 2, 2, 3, 3, 3]
STRUM_MAP = [ tune[0], tune[1] + string2, tune[1] + string1, tune[1], tune[2] + string2, tune[2] + string1, tune[2], tune[3] + string2, tune[3] + string1, tune[3] ]

mpr4_map = [ [0, 12], [0, 13], [0, 14], [1, 12], [1, 13], [1, 14], [2, 12], [2, 13], [2, 14], [3, 12], [3, 13], [3, 14] ]



def sensorToFret(mpr, sensor):
    if mpr < 4:
        return [mpr, sensor]

    elif mpr == 4:
        return mpr4_map[sensor]

    elif mpr == 5:
        return [mpr, sensor]


def fretToNote(fret):
    global mode
    if mode == ORGAN:
        return transpose + organ_tune[fret[0]][fret[1]]
    else:
        return transpose + tune[fret[0]] + fret[1]


recentFret = [0, 0, 0, 0]
activeNotes = [[[] for f in range(16)] for s in range(5)]



# Touch sensor setup
currentTouched = [list(s.touched_pins) for s in sensors]
oldTouched = currentTouched
print(currentTouched)

oldTouched = [list(t) for t in currentTouched]



# On fret pressed

def onAction(fret, status):
    global mode
    global transpose
    global tune
    global recentFret
    global activeNotes
    global new_mode
    global midi_channel

    print(fret)
    print(status)

    f = sensorToFret(fret[0], fret[1])

    if mode == FREEPLAY:
        if fret[0] == 5:
            return

        if status:
            midi.send(NoteOn(fretToNote(f), velocity))
            hmidi.send(NoteOn(fretToNote(f), velocity))
            pixels[f[0]] = wheel(f[1] / 15 * 255)

        else:
            midi.send(NoteOff(fretToNote(f), velocity))
            hmidi.send(NoteOff(fretToNote(f), velocity))
            
    
    elif mode == ORGAN:
        if fret[0] == 5:
            return

        if status:
            midi.send(NoteOn(fretToNote(f), velocity))
            hmidi.send(NoteOn(fretToNote(f), velocity))
            pixels[f[0]] = wheel(f[1] / 15 * 255)

        else:
            midi.send(NoteOff(fretToNote(f), velocity))
            hmidi.send(NoteOff(fretToNote(f), velocity))
            

    elif mode == PLUCK: # this is FUCKIGN INSANE and needs to be completely replaced (all notes turn off when one turns off)
        if fret[0] < 5:
            if status:
                recentFret[f[0]] = f[1]
            else:
                for note in activeNotes[f[0]][f[1]]:
                    midi.send(NoteOff(note, velocity))
                    hmidi.send(NoteOff(note, velocity))

                activeNotes[f[0]][f[1]] = []

        if fret[0] == 5 and (fret[1] == 0 or fret[1] == 3 or fret[1] == 6 or fret[1] == 9) :
            affect = F_STRUM_MAP[f[1]]
            if status:
                midi.send(NoteOn(fretToNote([affect, recentFret[affect]]) + STRUM_MAP[f[1]], velocity))
                hmidi.send(NoteOn(fretToNote([affect, recentFret[affect]]) + STRUM_MAP[f[1]], velocity))

                activeNotes[affect][recentFret[affect]].append(fretToNote([affect, recentFret[affect]]) + STRUM_MAP[f[1]])

                pixels[affect] = wheel(f[1] / 15 * 255)

            else:
                for n in activeNotes[F_STRUM_MAP[f[1]]]:
                    for note in n:
                        midi.send(NoteOff(note, velocity))
                        hmidi.send(NoteOff(note, velocity))
                    activeNotes[F_STRUM_MAP[f[1]]] = [[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[]]


    elif mode == TSTR: # this is FUCKIGN INSANE and needs to be completely replaced (all notes turn off when one turns off)
        if fret[0] < 5:
            if status:
                recentFret[f[0]] = f[1]
            else:
                for note in activeNotes[f[0]][f[1]]:
                    midi.send(NoteOff(note, velocity))
                    hmidi.send(NoteOff(note, velocity))

                activeNotes[f[0]][f[1]] = []

        if fret[0] == 5:
            affect = F_STRUM_MAP[f[1]]
            if status:
                midi.send(NoteOn(fretToNote([affect, recentFret[affect]]) + STRUM_MAP[f[1]], velocity))
                hmidi.send(NoteOn(fretToNote([affect, recentFret[affect]]) + STRUM_MAP[f[1]], velocity))

                activeNotes[affect][recentFret[affect]].append(fretToNote([affect, recentFret[affect]]) + STRUM_MAP[f[1]])

                pixels[affect] = wheel(f[1] / 15 * 255)

            else:
                for n in activeNotes[F_STRUM_MAP[f[1]]]:
                    for note in n:
                        midi.send(NoteOff(note, velocity))
                        hmidi.send(NoteOff(note, velocity))
                    activeNotes[F_STRUM_MAP[f[1]]] = [[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[]]


                pass
                #midi.send(NoteOff(fretToNote([affect, recentFret[affect]]) + STRUM_MAP[f[1]], velocity))
                #hmidi.send(NoteOff(fretToNote([affect, recentFret[affect]]) + STRUM_MAP[f[1]], velocity))


    elif mode == CHORD:
        pass


    elif mode == SET:
        if fret[0] == 5:
            return
        f = sensorToFret(fret[0], fret[1])

        if status:
            if f[0] == 3: # Transpose
                if f[1] < 13:
                    transpose = math.floor(transpose / 12) * 12 + f[1]

                elif f[1] == 13:
                    transpose -= 12

                elif f[1] == 14:
                    transpose += 12

            elif f[0] == 2: # Tune
                if f[1] < 3:
                    tune = INS[f[1]]

            elif f[0] == 1: # Mode
                if f[1] < len(modes) - 1:    # mode set + memory
                    mode = f[1] + 1
                    new_mode = mode
                    print(mode)
                                
                elif f[1] == 13:             # select MIDI channel to output to
                    midi_channel -= 1        # & display in binary on LEDs
                    if midi_channel < 1:
                        midi_channel = 1
                    elif midi_channel > 16:
                        midi_channel = 16
                    print(midi_channel)
                    
                    for p in range(4):
                        pixels[p] = [int(list(decimal_to_binary(midi_channel, 4))[p]) * v for v in wheel(midi_channel * p / 60 * 255)]
                    
                    hmidi.out_channel = midi_channel - 1
                    midi.out_channel = midi_channel - 1
                        
                elif f[1] == 14:
                    midi_channel += 1
                    if midi_channel < 1:
                        midi_channel = 1
                    elif midi_channel > 16:
                        midi_channel = 16
                    print(midi_channel)
                    
                    for p in range(4):
                        pixels[p] = [int(list(decimal_to_binary(midi_channel, 4))[p]) * v for v in wheel(midi_channel * p / 60 * 255)]
                    
                    hmidi.out_channel = midi_channel - 1
                    midi.out_channel = midi_channel - 1
                    
                


# Main loop

def decimal_to_binary(n, l):
    if n == 0:
        return "0" * l
    binary_string = ""
    while n > 0:
        remainder = n % 2
        binary_string = str(remainder) + binary_string
        n //= 2
    binary_string = (l - len(binary_string)) * "0" + binary_string
    return binary_string[-l:]
    

while True:
    # Reset changed sensors
    oldTouched = [list(t) for t in currentTouched]

    if not set_pin.value:
        prev_mode = mode
        mode = SET
    else:
        mode = new_mode


    try:
        # Pass thru to UART
        msg = midi.receive()
        if msg is not None:
            print("usb midi recieved: ")
            print(msg)
            hmidi.send(msg)

        msg = hmidi.receive()
        if msg is not None:
            print("uart midi recieved:")
            midi.send(msg)
            hmidi.send(msg)

    except TypeError:
        print("te")


    # Update touch sensors & trigger if pressed
    for s in range(len(sensors)):
        currentTouched[s] = sensors[s].touched_pins
        for f in range(len(currentTouched[s])):
            if currentTouched[s][f] != oldTouched[s][f]:
                try:
                    onAction([s,f], currentTouched[s][f])
                except ValueError:
                    pass

