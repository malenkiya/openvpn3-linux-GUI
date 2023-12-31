DISTRO=focal


sudo apt-get install curl wget
sudo mkdir -p /etc/apt/keyrings && curl -fsSL https://packages.openvpn.net/packages-repo.gpg | sudo tee /etc/apt/keyrings/openvpn.asc
sudo rm etc/apt/sources.list.d/openvpn-packages.list
echo "deb [signed-by=/etc/apt/keyrings/openvpn.asc] https://packages.openvpn.net/openvpn3/debian $DISTRO main" | sudo tee /etc/apt/sources.list.d/openvpn-packages.list 
sudo apt update
sudo apt install openvpn3
sudo apt install openvpn-dco-dkms 
wget https://github.com/malenkiya/openvpn3-linux-GUI/raw/main/openvpn-saml.deb
sudo dpkg -i openvpn-saml.deb

