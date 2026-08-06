# 基础镜像
FROM python:3.12-slim

# 设置工作目录
WORKDIR /app

# 复制依赖文件（先复制以利用 Docker 层缓存）
COPY requirements.txt ./

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
#RUN pip install --progress-bar off mcp==1.25.0 -i https://mirrors.aliyun.com/pypi/simple/

# 复制项目全部代码
COPY . .

RUN ln -snf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime && echo "Asia/Shanghai" > /etc/timezone

# 设置环境变量（如有 .env 可取消注释）
#COPY .env .env

ARG ENV
ARG WORKFLOW_SCENE_TYPE

ENV ENV=${ENV}
ENV WORKFLOW_SCENE_TYPE=${WORKFLOW_SCENE_TYPE}

# src/ 布局：让 goalflow 包可被导入
ENV PYTHONPATH=/app/src:/app


# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "goalflow.app:app", "--host", "0.0.0.0", "--port", "8000","--workers","2"]