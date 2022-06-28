# ACIDS 2022 NIME Workshop #3
-------

## Overview

 This guide will help you setup everything you need for the ACIDS 2022 NIME Workshop #3

## Requirements

- Computer (All OSes should work)
- Raspberry Pi 4 (3b+ is possible but will probably lag a bit)
- Ethernet cable (Wifi is possible, but you'll need to connect manually)

## Install Raspberry Pi OS Lite 64bits
[Direct Download Link](https://downloads.raspberrypi.org/raspios_lite_arm64/images/raspios_lite_arm64-2022-04-07/2022-04-04-raspios-bullseye-arm64-lite.img.xz) (from the [Raspberrypi's website](https://www.raspberrypi.com/software/operating-systems/))  

(If you're using a RaspberryPi 3 download the 32bits version)

## Flash the OS onto your microSD card
[Raspberry Pi Imager](https://www.raspberrypi.com/software/) is the quick and easy way to install an operating system to a microSD card ready to use with your Raspberry Pi.

- Insert your microSD card in your computer
- Open Raspberry Pi Imager, click on "Choose OS" then "Use a Custom Image" and select the iso you just downloaded.
- Select the microSD as the target destination
- Launch the write process

## Enable ssh to allow remote login
For security reasons, ssh is no longer enabled by default. To enable it you need to **create an empty file named ssh** (no extension) **in the root of the boot disk** (the microSD you just flashed)

## WIFI only: add your network info
Create a file in the root of boot called: ``wpa_supplicant.conf`` then paste
```
country=US
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1

network={
    ssid="NETWORK-NAME"
    psk="NETWORK-PASSWORD"
}
```
 (adjusting for your [ISO 3166 alpha-2 country code](https://en.wikipedia.org/wiki/List_of_ISO_3166_country_codes), network name and network password)

## Ethernet
Just connect your RaspberryPi to your router using an ethernet cable

## Get your RaspberryPi ip adress
either:
- connect your rapsberrypi to a monitor & a keyboard, open a terminal and type ``ifconfig``
- check your modem admin panel for connected equipements
- scan your network with ``sudo nmap -sn 192.168.1.0/24`` (will probably not work on complex networks like those used in companies, universities etc...)

## Connect using SSH
from your computer: ``ssh pi@{IP_ADDRESS}``

```
sudo apt-get update -y
sudo apt-get install git pip libportaudio2 libsndfile1 -y

git clone {REPO_HTTPS}
pip install -r Requirements.txt
