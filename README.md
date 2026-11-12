# Mihomo 个人代理面板

一个供个人管理多个 SOCKS5 服务的小项目：多个 Clash 订阅、节点分类筛选、每个服务独立选择出口、自动生成用户名和强密码。页面只保留服务、节点和订阅。

界面采用 shadcn 风格的黑白灰样式，采用紧凑卡片，支持服务搜索和运行状态筛选，适配桌面和手机。订阅、地区、标签等下拉框均可输入关键词模糊搜索；地区支持常用代码和拼音简写，节点搜索支持多个关键词组合。

使用 Python、SQLite 和 systemd，不需要 Docker、PostgreSQL 或前端构建。网页以普通系统账号运行，通过仅本机可访问的 UNIX socket 请求 root 管理进程创建独立 Mihomo 实例。控制接口关闭，每个实例只使用所选节点，不设置 DIRECT 回退。

## 支持环境

- Debian 12、Ubuntu 24.04，使用 systemd 的主机。
- x86_64 或 ARM64，Python 3.11+、SQLite 3.35+。
- 安装、升级和迁移由 root 执行，需要访问系统软件源、Python 包索引及 GitHub。
- 内核固定为 Mihomo 1.19.32，按架构通过官方发布页或官方 API 下载并验证 SHA-256。内核单独下载，不包含在源码包中；许可证见 [Mihomo](https://github.com/MetaCubeX/mihomo/blob/Meta/LICENSE)。

## 全新部署

将发布包复制到新服务器，校验、解压后运行：

```bash
sha256sum -c mihomo-panel-1.0.4.tar.gz.sha256
tar -xzf mihomo-panel-1.0.4.tar.gz
cd mihomo-panel-1.0.4
sudo ./install.sh --public-ip 203.0.113.10
```

`203.0.113.10` 是示例，请换成服务器公网 IP 或域名。首次安装为空白面板，不带任何真实订阅、节点或用户数据。初始账号为 `admin`；未提供 `ADMIN_PASSWORD` 时生成随机密码，保存在 `/etc/mihomo-panel/initial-admin.txt`。重复安装不会重置密码。

### 从 GitHub 部署与设置密码

```bash
git clone https://github.com/verus000/mihomo-panel.git
cd mihomo-panel
read -r -s -p '管理员初始密码（至少 16 个字符）：' ADMIN_PASSWORD
echo
export ADMIN_PASSWORD
sudo --preserve-env=ADMIN_PASSWORD ./install.sh --public-ip 203.0.113.10
unset ADMIN_PASSWORD
```

密码通过环境变量传入，不需要修改源码。输入内容不显示在终端，也不出现在命令行参数或安装日志中。已经使用 root 时，可直接执行 `./install.sh --public-ip 203.0.113.10`。

| 环境变量 | 作用 |
| --- | --- |
| `ADMIN_PASSWORD` | 首次创建管理员时使用，16–128 个字符。留空自动生成随机密码；已有管理员时忽略，后续通过面板修改密码。 |
| `FERNET_KEY` | 首次安装可选的 Fernet 加密密钥。留空自动生成；以后继续使用已安装的密钥，避免无法解密已有数据。 |

需要自行提供密钥时，可在具备 `cryptography` 的 Python 环境中通过 `Fernet.generate_key().decode()` 生成，然后导出 `FERNET_KEY`。使用 sudo 安装时通过 `--preserve-env=ADMIN_PASSWORD,FERNET_KEY` 传入。

安装器只将管理员密码的加盐哈希写入数据库。通过 `ADMIN_PASSWORD` 提供的明文不会写入 `web.env` 或初始密码文件。SOCKS5 密码仍按服务独立生成或在面板中配置，加密后保存在运行数据库中；真实订阅链接、节点密钥和账号数据均不属于源码。

默认监听本机 `127.0.0.1:8080`。可以通过 SSH 隧道体验：

```bash
ssh -N -L 8080:127.0.0.1:8080 root@203.0.113.10
```

浏览器打开 `http://127.0.0.1:8080`。需要直接从公网体验时，明确指定监听地址：

```bash
sudo ./install.sh --public-ip 203.0.113.10 --bind 0.0.0.0 --port 8080
```

公网 HTTP 入口适合临时体验；长期使用建议通过自己的 HTTPS 反向代理访问本机监听。云安全组需放行面板使用的 TCP 端口，以及所建代理端口的 TCP/UDP。

可配置参数：

| 参数 | 作用 |
| --- | --- |
| `--public-ip IP或域名` | 生成连接信息时使用的公网地址 |
| `--bind 地址` | 默认 `127.0.0.1`；直接公网监听使用 `0.0.0.0` |
| `--port 端口` | 面板端口，默认 `8080` |
| `--hosts panel.example.com` | 允许访问面板的域名，多个用逗号分隔 |
| `--cookie-secure 1` | 自己配置 HTTPS 后启用 Secure Cookie |
| `--firewall off` | 自行管理防火墙；默认 `auto` |
| `--skip-packages` | 系统依赖已安装时跳过 apt |
| `--core-file /path/to/mihomo.gz` | 使用提前下载的对应版本压缩包，仍强制校验 |

自动防火墙只维护自身命名空间及带 `mihomo-panel:` 注释的规则，不清空原有规则。它在现有 nftables input 基础链中加入相应端口放行，支持存在默认丢弃策略的主机。其他工具重新加载防火墙后，请重启 `mihomo-panel-manager` 重新应用规则；复杂的 UFW/firewalld/自定义策略建议使用 `--firewall off` 自行配置。安装程序不会额外启用或重写系统 nftables 服务。

## 升级

解压新发布包，在新目录执行：

```bash
sudo ./upgrade.sh
sudo ./doctor.sh
```

先准备新代码、独立 Python 环境和内核，再短暂停止面板与管理进程。现有代理进程继续运行。升级前自动备份数据库与密钥；启动健康检查失败时恢复原代码、配置和数据库。未指定的公网地址、监听地址和端口继续保留。

**升级内核文件不会自动重启现有代理**。在面板中重启对应服务后使用其 systemd 单元所指定的内核。较早手工创建的实例可能仍使用原有内核路径；跨机器恢复时会生成使用项目内核的新单元。

## 备份和换机器

旧机器上执行：

```bash
sudo ./backup.sh /root/panel-backup
```

备份目录必须尚不存在。备份时短暂停止面板和管理进程，已有代理继续运行。目录包含数据库、加密密钥、服务清单和完整性校验，不需要复制旧机器的虚拟环境、系统账号或 systemd 单元。

将整个备份目录通过 SSH/SCP 等方式私下传到新机器，先按上面的方法安装空白面板，再执行：

```bash
sudo ./restore.sh /root/panel-backup
sudo ./doctor.sh
```

恢复会保留新机器的公网 IP、面板监听和域名设置，恢复原登录密码、订阅、节点分类、SOCKS5 用户名/密码和端口，并重新创建系统账号、Mihomo 配置、独立单元与开机启动设置。已有客户端需改为新服务器地址；新机器仍需配置云安全组。恢复之前会验证备份及全部加密数据，失败时尝试恢复操作前的实例。

目标机器已有订阅或服务时，明确覆盖需要：

```bash
sudo ./restore.sh /root/panel-backup --replace
```

恢复和覆盖恢复会短暂中断目标机器上由面板管理的代理。恢复前自动备份保存在 `/var/backups/mihomo-panel/`。备份包含可恢复的密码和密钥，目录权限为 `700`，文件权限为 `600`；不要提交到 Git 或放在网页静态目录。

## 卸载

```bash
sudo ./uninstall.sh
```

卸载前自动备份，移除本项目管理的网页服务、代理实例、账号和规则；默认保留 SQLite、加密密钥和登录密码，重新安装即可重建实例。

确认需要删除运行数据时：

```bash
sudo ./uninstall.sh --purge
```

`--purge` 仍保留 `/var/backups/mihomo-panel/` 中的卸载前备份。其他服务、防火墙规则以及独立安装的 Mihomo 内核不属于清理范围。

## 文件与日常检查

| 位置 | 内容 |
| --- | --- |
| `/opt/mihomo-panel/` | 程序、独立虚拟环境与 `core/mihomo` |
| `/etc/mihomo-panel/web.env` | 机器配置与加密密钥，`root:mihomo-panel 640` |
| `/var/lib/mihomo-panel/panel.sqlite3` | SQLite，`mihomo-panel 600`，开启 WAL 和外键 |
| `/var/lib/mihomo-panel-manager/services.json` | root 管理的实例登记 |
| `/etc/mihomo/<服务标识>/config.yaml` | 各代理配置，`root:对应实例组 640` |
| `/var/backups/mihomo-panel/` | 升级、恢复和卸载前的私有备份 |

```bash
sudo ./doctor.sh
systemctl status mihomo-panel mihomo-panel-manager
journalctl -u mihomo-panel -n 60 --no-pager
```

保留 `web.env` 中原有 `FERNET_KEY`，不要在升级时重新生成；单独复制 SQLite 主文件也可能遗漏 WAL 数据，应使用备份命令。

## 开发与发布

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
python3 build-release.py
```

发布包通过明确的文件清单构建，不包含环境配置、数据库、备份、真实订阅或内核二进制。`requirements.txt` 只包含运行依赖，浏览器与测试依赖在 `requirements-dev.txt`。

仓库只保存源码和不含真实密钥的 `config.env.example`。`.gitignore` 已排除本地环境文件、数据库、备份、初始密码文件、密钥与部署包；真实机器数据单独保管。
