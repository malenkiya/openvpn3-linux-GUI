#!/bin/bash

# Detect the distribution code name
DISTRO=$(lsb_release -cs)

# Check if the distribution is supported
if [[ "$DISTRO" != "focal" && "$DISTRO" != "jammy" ]]; then
  echo "Warning: Unsupported distribution $DISTRO. Proceeding with installation, but it may not work as expected."
fi

# Install necessary packages
sudo apt-get -y install curl wget

# Set up OpenVPN3 repository
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://packages.openvpn.net/packages-repo.gpg | sudo tee /etc/apt/keyrings/openvpn.asc

# Remove existing OpenVPN sources list if it exists
sudo rm -f /etc/apt/sources.list.d/openvpn-packages.list

# Add OpenVPN repository
echo "deb [signed-by=/etc/apt/keyrings/openvpn.asc] https://packages.openvpn.net/openvpn3/debian $DISTRO main" | sudo tee /etc/apt/sources.list.d/openvpn-packages.list

# Update package lists
sudo apt -y update

# Install required packages
sudo apt install -y libxcb-cursor0
sudo apt install -y openvpn3
sudo apt install -y openvpn-dco-dkms

# Download and install the OpenVPN GUI package
wget https://github.com/malenkiya/openvpn3-linux-GUI/releases/download/0.3/openvpn-saml.deb
sudo dpkg -i openvpn-saml.deb
