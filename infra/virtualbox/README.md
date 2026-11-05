# 独立 VirtualBox Docker 环境

这里的脚本只允许创建名为 `nebula-text2sql-docker` 的新虚拟机，默认磁盘位于
`E:\test2\virtualbox`。如果同名虚拟机已存在，脚本会直接退出，不会修改、启动、停止或删除
任何现有虚拟机。

1. 准备 Ubuntu Server 24.04 LTS ISO。
2. 在 `E:\test2` 下创建仅含虚拟机登录密码的一行文本文件，例如
   `E:\test2\virtualbox-password.txt`；不要提交该文件。
3. 在 PowerShell 中运行：

   `powershell -ExecutionPolicy Bypass -File infra/virtualbox/create-isolated-vm.ps1 -IsoPath <ISO绝对路径> -PasswordFile E:\test2\virtualbox-password.txt -Start`

4. 脚本会无人值守安装 Ubuntu、OpenSSH、Docker Engine 和 Compose v2。安装完成后通过
   `ssh -p 22222 text2sql@127.0.0.1` 登录。
5. 把本项目复制到虚拟机，复制 `.env.example` 为 `.env`，更换密码后运行
   `docker compose up --build -d`。

也可以先制作排除 `.git`、`.conda`、`.downloads`、`node_modules` 和训练输出的 tar.gz，
再用 `scripts/deploy_virtualbox.py` 等待 SSH、SFTP 上传并启动 Compose。脚本从密码文件读
取凭据，不会打印密码，并会写出不含秘密的部署报告。

production 部署必须配置 API 鉴权。已有 `.env` 可通过 `--env-file .env` 由部署脚本使用
SFTP 上传到临时路径，再以 `0600` 权限原子替换目标文件；部署报告只记录
`env_uploaded: true`，不会保存任何环境变量值。未传该参数时继续保留虚拟机上的现有
`.env`。

宿主机端口使用 15173、18000、15432 和 16379，避开 Docker 常见默认端口，降低与其他
项目冲突的风险。VirtualBox 不适合作为 NVIDIA CUDA 训练环境；QLoRA 应直接使用宿主机
CUDA/WSL2 或另一台可透传 GPU 的 Linux 机器。
