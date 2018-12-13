# DogCam
This is a simple camera capture and web server script to stream data from a
Raspberry Pi camera to a web browser. I use it to see what my dogs throughout 
the day.

**WARNING**: This is insecure. There is no password protection or
SSL protection.


## Hardware
The hardware includes:

- Raspberry Pi Zero W (with Wifi)
- Official case for Raspberry Pi Zero
- 8 GB micro SD card
- Raspberry Pi Camera Module (v2)


Everything but the camera were purchasd as a bundle:

- [https://www.amazon.com/gp/product/B06XJQV162/]
- [https://www.amazon.com/gp/product/B01ER2SKFS/]

Total cost is around $50. I used existing montiors and keyboards for initial
setup.


## Software
Once the hardware is set up and assembled, the following steps will get it
going.

- Set up Wifi using `sudo raspi-config`. More details available
  [here](https://www.raspberrypi.org/documentation/configuration/wireless/wireless-cli.md).
- Ensured python v3 and virtualenv were installed. You may need to `sudo
  apt-get install python3 virtualenv` or something like that.
- Copy this repository into a directory like `~/dogcam`
- In that directory, create a new environment `virtualenv env`
- Install the dependencies: `env/bin/pip install -r requirements.txt`
- Run the script in the background `env/bin/python3 webstream.py 8000 &` to
  serve on port 8000

Note to access outside the home, the port must be opened on your router.


## Implementation
There are three components, the image capture, the motion detection, and the
web server. The image capture is performed using community tools for the
raspberry pi, and motion detection using CV2. In order to do the capture,
motion detection, and web service through a single script, maintaining
simplicity, and avoid the challenges of multithreaded or multiprocess
programming, the new asynchronous capabilities of python were used, using
aiohttp as the webserver, and adapting the camera utilities to work in an
asynchronous manner.

This was also my chance to experiment with the new async tools.
