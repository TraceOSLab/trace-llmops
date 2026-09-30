from flask_weaviate import FlaskWeaviate

# 只创建扩展；客户端在应用上下文中首次访问 .client 时连接，退出时自动关闭。
weaviate = FlaskWeaviate()
