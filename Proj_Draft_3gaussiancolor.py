import machine, neopixel, utime, math
from vl53l1x import VL53L1X
from machine import Pin, ADC, PWM, I2C

paint_mode = False

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

def expected_surface_distance(theta):
    center_dist = 330  # mm straight ahead
    c = math.cos(theta)
    if c < 0.1:   # avoid division by zero near 90°
        c = 0.1
    return center_dist / c


def x_poltocart(theta):
    x = 450 * math.sin(theta)
    return x

def y_poltocart(distance_mm, theta):
    y = distance_mm * math.cos(theta)
    return y

def normalizeColor(t):
    R = int(max(0, min(255, 255*math.exp(-(t**2)/0.04))))
    G = int(max(0, min(255, 255*math.exp(-((t-0.5)**2)/0.04))))
    B = int(max(0, min(255, 255*math.exp(-((t-1.0)**2)/0.04))))
    color = (R, G, B)
    return color

def range_to_LED(x_mm, y_mm, distance_cm, LED_array, theta, paintBool):
    # for fading the old LEDs (Copilot)
        
    if not paintBool: # if in tracing mode
        fade_factor = 0.9
        for i in range(NUM_LEDS):
            r, g, b = LED_array[i]
            LED_array[i] = (int(r * fade_factor), int(g * fade_factor), int(b * fade_factor))

    # x → LED index
    x_range_mm = 450
    distancePerLED = x_range_mm / NUM_LEDS
    led_index = int((x_mm + 225) / distancePerLED)

    if not (0 <= led_index < NUM_LEDS):
        return LED_array
        clear_digits()
    else:
        display_number(int(y))
    # dynamic distance normalization (Copilot)
    expected = expected_surface_distance(theta)
    min_dist = 30  # mm
    
# Takes minimum of the LiDAR distance and Servo geometry expected distance
# Then takes maximum between minimum distance bound to make sure the distance is meaningful
    d = max(min_dist, min(y_mm, expected))
    
# Normalize the distance d to some value between 0 and 1 for easier color mappin'
    t = (d - min_dist) / (expected - min_dist)
    t = max(0, min(1, t))
    
    # Color mapping
    color = normalizeColor(t)
    print(color, t)
    
    if paintBool:
        LED_array[led_index] = color
    else:
        # fade + add
        r, g, b = LED_array[led_index]
        LED_array[led_index] = (
            min(255, r + color[0]),
            min(255, g + color[1]),
            min(255, b + color[2]),
        )
    return LED_array

def read_distance_avg(n=5):
    total = 0
    for i in range(n):
        total += distance.read()
    return total / n

# Main loop
while True:
    now = utime.ticks_ms()

    # Read joystick
    xValue = xAxis.read_u16()
    yValue = yAxis.read_u16()
    buttonValue = button.value()

    # Servo direction is y-axis
    if yValue < Y_DOWN_THRESHOLD:
        direction = -0.5
    elif yValue > Y_UP_THRESHOLD:
        direction = 0.5
    else:
        direction = 0

    # Move servo slowly
    if direction != 0:
        servo_angle = set_angle(servo_angle, direction)

    # Update LiDAR LED
    # dist_mm = distance.read()
    dist_mm = read_distance_avg()
    dist_cm = dist_mm / 10

    # convert to radians for math.sin and cos and for 0° = centered 
    theta = math.radians(servo_angle-135)
    
    x = x_poltocart(theta)
    y = y_poltocart(dist_mm, theta)
    
    print("Servo angle: ", servo_angle - 135, "  range: mm ", dist_mm, "  x: mm ", x, "  y: mm ", y, " paintmode: ", paint_mode)
    
    if buttonValue == 0:
        paint_mode = not paint_mode
        utime.sleep_ms(200)
        
    LED_array = range_to_LED(x, y, dist_cm, LED_array, theta, paint_mode)
    
    # display_number(int(y)) # Displays top-down cartesian distance
    
    # 4. Write to LED Strip
    for i in range(NUM_LEDS):
        pixels[i] = LED_array[i]
    pixels.write()
    utime.sleep_ms(10)

servo.deinit()


