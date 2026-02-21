点点素材管理大师 - 说明

对用户指定文件夹下的原始素材（图片、视频、音频）按拍摄日期与媒体种类分类整理，视频与图片下再按拍摄设备分子目录；移动时会将与主文件高度关联的同名/同词干文件一并移动。

一、功能概览

  扫描目录    递归扫描用户指定的源文件夹
  媒体分类    图片 / 视频（含全景、360）/ 音频
  按日期      目标结构：日期/媒体类型/[设备]/
  按设备      图片、视频（含全景）下按设备建子文件夹
  关联文件    同目录下与主文件同词干的文件一并移动（如 .xmp、.srt、同名侧边文件）
  保留原位    可配置扩展名（如 .op、.ed、.lrprev）不参与移动

二、目标目录结构示例

  输出根目录/
  ├── 2024-01-15/
  │   ├── 图片/
  │   │   ├── Apple iPhone 14 Pro/
  │   │   │   ├── IMG_001.jpg
  │   │   │   └── IMG_001.xmp
  │   │   └── 未知设备/
  │   ├── 视频/
  │   │   └── Canon EOS R5/
  │   └── 全景视频/
  │       └── Insta360 ONE X2/
  ├── 2024-02-01/
  │   ├── 图片/
  │   └── 音频/
  │       └── 未知设备/
  └── 无日期/
      └── 图片/

三、使用方式

  1. 配置
  编辑项目根目录下的 config.json：
  - source_path：要整理的素材文件夹（也可在 GUI/命令行中指定）
  - output_path：整理后的根目录（留空则视为与源相同，在源下建日期/类型子目录）
  - image_extensions / video_extensions / audio_extensions：参与整理的扩展名
  - leave_in_place_extensions：不移动的扩展名（如同步软件状态文件）
  - related_same_stem：是否将同词干文件一并移动
  - date_fallback：无法从元数据取日期时用 mtime 等
  - use_exiftool：是否尝试用 exiftool 读取日期/设备（需系统已安装 exiftool）

  2. 命令行
  # 指定源与输出
  python run_scan.py --source "D:\我的素材" --output "D:\整理后"
  # 试运行（不移动文件）
  python run_scan.py --source "D:\我的素材" --dry-run
  # 清空日志
  python run_scan.py --reset-log

  3. GUI（推荐）
  python main.py
  在界面中选择源文件夹、输出根目录：
  - 勾选「试运行」：按钮显示「开始扫描」，仅扫描并输出报告；
  - 不勾选：按钮显示「开始整理」，执行整理并输出任务报告。

四、依赖

  - Python 3.8+
  - Pillow：图片 EXIF（日期、设备）
  - hachoir-metadata：视频/音频元数据（日期等）
  - 可选：系统安装 exiftool 可提升视频/音频的日期与设备识别率

  安装：pip install -r requirements.txt
  （可选）安装 exiftool：Windows 可下载 ExifTool 并加入 PATH。

五、版本与日志

  - 版本见 media_organizer.__version__。
  - 日志文件：media_organizer.log。

六、Docker 交付

  每次交付会提供镜像 tar 包（sucai-zhengliqi-vX.Y.tar），用户可 docker load 后直接运行。
  打包命令：python build_docker.py
  详见 docs/交付说明.txt。
