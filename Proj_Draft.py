import machine, neopixel, utime, math
from vl53l1x import VL53L1X
from machine import Pin, ADC, PWM, I2C

# LED strip setup
NUM_LEDS = 10
LED_PIN = 16
pixels = neopixel.NeoPixel(Pin(LED_PIN), NUM_LEDS)

# Joystick LED cursor
current_led = NUM_LEDS // 2
MOVE_INTERVAL = 120
last_move = utime.ticks_ms()

# Joystick setup
button = Pin(28, Pin.IN, Pin.PULL_UP)
xAxis = ADC(Pin(27))  # VRx
yAxis = ADC(Pin(26))  # VRy

# Extreme thresholds
LEFT_THRESHOLD  = 8000
RIGHT_THRESHOLD = 57500
Y_DOWN_THRESHOLD = 8000
Y_UP_THRESHOLD   = 57500

# Servo setup
servo_angle = 135
minAngle = 90
maxAngle = 180

servo = PWM(Pin(17))
servo.freq(50)

def set_angle(current_angle, change):
    new_angle = current_angle + change
    new_angle = max(minAngle, min(maxAngle, new_angle))
    duty = int(((new_angle / 180) * (8191 - 1638)) + 1638)
    servo.duty_u16(duty)
    return new_angle

# 7-Segment setup
SEGMENTS = {
    0: (1,1,1,1,1,1,0,0),
    1: (0,1,1,0,0,0,0,0),
    2: (1,1,0,1,1,0,1,0),
    3: (1,1,1,1,0,0,1,0),
    4: (0,1,1,0,0,1,1,0),
    5: (1,0,1,1,0,1,1,0),
    6: (1,0,1,1,1,1,1,0),
    7: (1,1,1,0,0,0,0,0),
    8: (1,1,1,1,1,1,1,0),
    9: (1,1,1,1,0,1,1,0),
}

# Segment pins
segA = Pin(21, Pin.OUT)
segB = Pin(22, Pin.OUT)
segC = Pin(13, Pin.OUT)
segD = Pin(15, Pin.OUT)
segE = Pin(14, Pin.OUT)
segF = Pin(20, Pin.OUT)
segG = Pin(12, Pin.OUT)

segments = [segA, segB, segC, segD, segE, segF, segG]

# Digit select pins (3 digits)
digit_pins = [
    Pin(19, Pin.OUT),  # hundreds
    Pin(18, Pin.OUT),  # tens
    Pin(11, Pin.OUT),  # ones
]

def set_segments(num):
    pattern = SEGMENTS.get(num, (0,0,0,0,0,0,0))
    for pin, val in zip(segments, pattern):
        pin.value(val)

def clear_digits():
    for d in digit_pins:
        d.value(1)
        
def display_number(n):
    n = int(n)
    n = max(0, min(999, n))

    digits = [
        n // 100,
        (n // 10) % 10,
        n % 10
    ]

    for i in range(3):
        clear_digits()
        set_segments(digits[i])
        digit_pins[i].value(0)
        utime.sleep_us(800)  # faster refresh!

# LiDAR setup
i2c = I2C(0, scl=Pin(1), sda=Pin(0), freq=400000)
distance = VL53L1X(i2c)

# LED array for LiDAR colors
LED_array = [(0, 0, 0)] * NUM_LEDS

def expected_surface_distance(angle): # Distance to surface from SERVO POV
    center_dist = 330   # mm when servo is centered
    edge_dist   = 465   # mm when servo is at maxAngle
    t = (angle - minAngle) / (maxAngle - minAngle)
    return center_dist + t * (edge_dist - center_dist)

def range_to_LED(distance_cm, LED_array, angle):
    # for fading the old LEDs (Copilot)
    fade_factor = 0.9
    for i in range(NUM_LEDS):
        r, g, b = LED_array[i]
        LED_array[i] = (int(r * fade_factor), int(g * fade_factor), int(b * fade_factor))

    # Angle → LED index
    angle_range = maxAngle - minAngle
    angle_per_led = angle_range / NUM_LEDS
    led_index = int((angle - minAngle) / angle_per_led)

    if not (0 <= led_index < NUM_LEDS):
        return LED_array

    # dynamic distance normalization (Copilot)
    distance_mm = distance_cm * 10
    expected = expected_surface_distance(angle)
    min_dist = 30  # mm

# Takes minimum of the LiDAR distance and Servo geometry expected distance
# Then takes maximum between minimum distance bound to make sure the distance is meaningful
    d = max(min_dist, min(distance_mm, expected))
    
# Normalize the distance d to some value between 0 and 1 for easier color mappin'
    t = (d - min_dist) / (expected - min_dist) 

    # Color mapping
    if t < 0.1: # Purple for close objects
        color = (128, 0, 128)
        print("Purple", t)
    elif t < 0.2: # Transition from blue to purple
        color = (64, 0, 192)
        print("Blurple", t)
    elif t < 0.3: # Blue for somewhat close objects
        color = (0, 0, 255)
        print("Blue", t)
    elif t < 0.4: # Transition from green to blue
        color = (0, 64, 192)
        print("Teal", t)
    elif t < 0.5: # Transition from green to blue
        color = (0, 192, 64)
        print("Grue", t)
    elif t < 0.6: # Green for medium distant objects
        color = (0, 255, 0)
        print("Green", t)
    elif t < 0.7: # Transition from yellow to green
        color = (128, 255, 0)
        print("Grellow", t)
    elif t < 0.8: # Yellow for somewhat far objects
        color = (255, 255, 0)
        print("Yellow", t)
    elif t < 0.9: # Orange for far objects
        color = (255, 32, 0)
        print("Orange", t)
    elif t < 1.0: # Red for very distant objects
        color = (255, 0, 0)
        print("Red", t)
    elif t < 1.05: # Red for very distant objects
        color = (128, 0, 0)
        print("Fading Red", t)
    else: # Red for very distant objects
        color = (64, 0, 0)
        print("Faded Red", t)
        
    # Add color
    r, g, b = LED_array[led_index]
    LED_array[led_index] = (
        min(255, r + color[0]),
        min(255, g + color[1]),
        min(255, b + color[2]),
    )

    return LED_array


# Main loop
while True:
    now = utime.ticks_ms()

    # Read joystick
    xValue = xAxis.read_u16()
    yValue = yAxis.read_u16()

    # Servo direction is y-axis
    if yValue < Y_DOWN_THRESHOLD:
        direction = -1
    elif yValue > Y_UP_THRESHOLD:
        direction = 1
    else:
        direction = 0

    # Move servo slowly
    if direction != 0:
        servo_angle = set_angle(servo_angle, direction)

    # Update LiDAR LED
    dist_mm = distance.read()
    dist_cm = dist_mm / 10
    
    # for i in range(30): Originally was going to display this multiple times per sec to remove flicker
    display_number(dist_mm)
        
    print("Servo angle: ", servo_angle, "  range: mm ", dist_mm)
    
    LED_array = range_to_LED(dist_cm, LED_array, servo_angle)

    # 4. Write to LED Strip
    for i in range(NUM_LEDS):
        pixels[i] = LED_array[i]

    pixels.write()

    utime.sleep_ms(10)

servo.deinit()
