# 生产 HTTPS 证书

在服务器的仓库根目录 `nginx/ssl/` 放置这两个文件：

```text
nginx/ssl/
├── llmops.qiuyouyou.cn_bundle.crt
└── llmops.qiuyouyou.cn.key
```

`llmops.qiuyouyou.cn_bundle.crt` 使用 PEM 格式，包含域名证书与中间证书链，域名证书放在最前面。`llmops.qiuyouyou.cn.key` 是与证书匹配的 PEM 私钥，需使用 Nginx 能无交互加载的版本。如果下载包中的文件名不同，可重命名为以上名称，或同步修改 `nginx/conf.d/default.conf` 中的两个路径。

Compose 将整个目录只读挂载到 `/etc/nginx/ssl`，文件无需复制进镜像。证书和私钥已被 Git 与 Docker 构建上下文忽略；本目录只提交这份说明，不放置占位证书或私钥。

上传文件后，从仓库根目录设置权限并检查配置：

```bash
chmod 644 nginx/ssl/llmops.qiuyouyou.cn_bundle.crt
chmod 600 nginx/ssl/llmops.qiuyouyou.cn.key
sudo docker compose -f compose.prod.yaml run --rm --no-deps llmops-nginx nginx -t
sudo docker compose -f compose.prod.yaml up -d --no-deps llmops-nginx
```

缺少文件、证书与私钥不匹配或读取权限不足时，Nginx 无法启动。更新证书后，重新检查并加载：

```bash
sudo docker compose -f compose.prod.yaml exec llmops-nginx nginx -t
sudo docker compose -f compose.prod.yaml exec llmops-nginx nginx -s reload
```

当前配置加载自行提供的证书，续期后需要替换文件并重新加载。域名解析、端口放行和 HTTPS 检查见 [生产部署说明](../../docs/runbooks/production.md)。证书链与权限要求参见 [Nginx HTTPS 文档](https://nginx.org/en/docs/http/configuring_https_servers.html)。
