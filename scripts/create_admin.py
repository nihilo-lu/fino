#!/usr/bin/env python3
"""
创建或重置管理员账号
用法: python scripts/create_admin.py [用户名] [密码]
若 conf/config.yaml 不存在，会从 config.example.yaml 复制并添加用户
"""
import os
import sys

# 确保项目根目录在路径中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    username = (sys.argv[1] if len(sys.argv) > 1 else input("用户名: ")).strip().lower()
    password = sys.argv[2] if len(sys.argv) > 2 else input("密码: ")

    if not username or not password:
        print("错误: 用户名和密码不能为空")
        sys.exit(1)
    if len(password) < 6:
        print("错误: 密码至少 6 位")
        sys.exit(1)

    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base, "conf", "config.yaml")
    example_path = os.path.join(base, "conf", "config.example.yaml")

    import yaml
    from yaml.loader import SafeLoader
    import bcrypt

    if not os.path.exists(config_path) and os.path.exists(example_path):
        print(f"复制 {example_path} 为 {config_path}")
        with open(example_path, "r", encoding="utf-8") as f:
            config = yaml.load(f, Loader=SafeLoader) or {}
    elif os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.load(f, Loader=SafeLoader) or {}
    else:
        config = {}

    if "credentials" not in config:
        config["credentials"] = {}
    if "usernames" not in config["credentials"]:
        config["credentials"]["usernames"] = {}

    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    config["credentials"]["usernames"][username] = {
        "email": "",
        "first_name": username,
        "password": hashed,
        "roles": ["admin"],
        "disabled": False,
    }

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print(f"已创建/更新用户: {username} (管理员)")
    print(f"配置文件: {config_path}")

if __name__ == "__main__":
    main()
