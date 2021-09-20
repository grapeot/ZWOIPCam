chmod 755 camera.service
cp ./camera.service /lib/systemd/system/
systemctl daemon-reload
systemctl enable camera.service
systemctl start camera.service
