## ZWO Astronomy Camera as IP Camera

Astronomy cameras are known for their high sensitivity and flexibility on whether to have IR pass through and bayer filters.
This makes them a perfect fit as an IP camera, no matter for all sky camera, baby monitoring, or stealth night monitoring.
This project enables us to use a ZWO camera, which I happen to have at hand, to act as an IP camera, so it could be connected with a DVR/NVR for continouous recording, or combined with other processing pipelines to provide more intelligent services (object detection etc.).
This project was tested on a Raspberry Pi 3 and Python 3, but I don't see a reason why it couldn't work on Raspberry Pi 4 or Nvidia Jetson or Python 2.

### Usage

1. Download ZWO ASI camera SDK from [their website](https://download.astronomy-imaging-camera.com/for-developer/) for your OS. Extract the content and put it to this project folder. You can also put it elsewhere. Just need to change the `SDK_PATH` variable in `main.py`. If you want to execute the code without root privilege, please follow the instructions in the `lib/README` of the SDK.
2. Use `python3 -m pip install -r requirements.txt` to install dependencies, which only contain a python binding to ZWO SDK for now.
3. Use `python3 main.py` to launch the monitor.
4. Use `http://<HOSTNAME>:8000/stream.mjpg` for the video stream, and `http://<HOSTNAME>:8000/latest_full.jpg` for the latest captured image.
5. This script can also be registered as a service, which automatically starts on system boot. We provide `camera.service` as a reference. In order to set it up, one could 1) change the `WorkingDirectory` in the `camera.service` file, and 2) run `enable_service.sh` with root privilege.

## 使用ZWO天文相机作为IP相机

天文相机拥有比普通相机高得多的灵敏度和灵活性。
比如可以透过红外线，或者没有贝尔滤镜（黑白相机）。
所以天文相机其实非常适合当IP相机来做监控，比如做全天相机监测云量和流星，监控小孩或者在没有红外补光灯的情况下在夜里监控。
这个项目可以让ZWO天文相机作为IP相机使用，比如可以和DVR/NVR录制设备连起来持续录像，或者和其他算法/工具连起来提供物体检测等智能应用。
本项目在树莓派 3 + Python 3上测试通过。但它应该也可以在树莓派4，NVidia Jetson，和Python 2上面直接跑。

### 使用方法

1. 从[官网](http://zwoasi.com/software)下载ZWO ASI相机SDK（需要点进“二次开发”）。解压到本项目的文件夹下。其实也可以把SDK目录放到其他地方，只要把`main.py`里面的`SDK_PATH`改一下就好。有一个小坑是需要看一下SDK的`lib/README`，跟着上面的步骤做一个简单的安装，这样才能不用root权限就可以运行。
2. 用`python3 -m pip install -r requirements.txt`安装依赖。
3. 用`python3 main.py`启动程序。
4. 用`http://<HOSTNAME>:8000/stream.mjpg`来访问视频串流，用`http://<HOSTNAME>:8000/latest_full.jpg`来访问最新的静态jpg图像。
5. 这个脚本还可以作为一个系统服务开机自启动。要安装系统服务，我们需要1) 把`camera.service`文件里面的`WorkingDirectory`改为实际存放的目录位置，2) 用管理员权限（sudo）执行`enable_service.sh`.