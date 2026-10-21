BioCaL website
==============
1. Upload the Arduino sketch provided in the earlier conversation. It must print readings as LDR:<0-1023> and accept LED1:1, LED2:1, LED3:1 and LEDn:0 commands at 9600 baud.
2. Install Python 3.10+.
3. In this folder run: pip install -r requirements.txt
4. Close Arduino Serial Monitor.
5. Run: python app.py
6. Open http://127.0.0.1:5000 and select your COM port.

Wiring: red LED D3, green LED D4, blue LED D5, each with 220 ohm resistor. LDR divider: 5V -> LDR -> A0 junction -> 10k resistor -> GND.

Live sensor values come from Arduino analogRead(A0). The working-principle canvas is illustrative. The OD calculation assumes ADC is proportional to light intensity and must be validated. ML is simple linear regression over calibration standards, not a validated model. One LDR gives one live reading at a time.
