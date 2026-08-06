import os
import oss2
from oss2.models import PartInfo
import logging
from typing import List, Optional
from tqdm import tqdm

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from goalflow.config import get_logger

logger = get_logger(__name__)


class OSSClient:
    """
    阿里云OSS客户端，支持文件上传和下载
    """
    
    def __init__(self, 
        access_key_id: str, 
        access_key_secret: str, 
        endpoint: str, 
        bucket_name: str
    ):
        """
        初始化OSS客户端
        
        Args:
            access_key_id: 阿里云访问密钥ID
            access_key_secret: 阿里云访问密钥Secret
            endpoint: OSS endpoint 
            bucket_name: 存储桶名称
        """
        self.access_key_id = access_key_id
        self.access_key_secret = access_key_secret
        self.endpoint = endpoint
        self.bucket_name = bucket_name
        
        # 创建认证对象
        self.auth = oss2.Auth(access_key_id, access_key_secret)
        
        # 创建Bucket对象
        self.bucket = oss2.Bucket(self.auth, endpoint, bucket_name)


    def upload_file(self,
            * ,
            local_file_path: str, 
            oss_object_key: str,
            expires:int = 3600*24*7 
        ) -> str:
        """
        上传文件到OSS
        
        Args:
            local_file_path: 本地文件路径
            oss_object_key: OSS对象键（文件在OSS中的路径）
        Returns:
            str: 文件对应的oss_url
        """
        try:
            if not os.path.exists(local_file_path):
                raise ValueError(f"本地文件不存在: {local_file_path}")
            
            result = self.bucket.put_object_from_file(oss_object_key, local_file_path)
            
            if result.status != 200:
                raise ValueError(f"文件上传失败: {result}")
            
            oss_url = self.bucket.sign_url('GET', oss_object_key, expires)
            
            return oss_url
                
        except Exception as e:
            logger.error(f"上传文件时发生错误: {str(e)}")
            raise e
        
    def upload_file_data(self, 
            *,
            data: bytes, 
            oss_object_key: str,
            expires:int = 3600*24*7 
        ) -> str:
        """
        上传文件到OSS
        
        Args:
            data:  文件二进制数据
            oss_object_key: OSS对象键（文件在OSS中的路径）
        Returns:
            str: 文件对应的oss_url
        """        
        try:
            result = self.bucket.put_object(oss_object_key, data)
            
            if result.status != 200:
                raise ValueError(f"文件上传失败: {result}")
            
            oss_url = self.bucket.sign_url('GET', oss_object_key, expires)
            
            return oss_url
                
        except Exception as e:
            logger.error(f"上传文件时发生错误: {str(e)}")
            raise e
    
    def download_file(self,
            *, 
            oss_object_key: str,
            local_file_path: str,
        ) -> bool:
        """
        从OSS下载文件
        
        Args:
            oss_object_key: OSS对象键（文件在OSS中的路径）
            local_file_path: 本地文件保存路径

        Returns:
            bool: 下载是否成功
        """
        try:
            # 检查OSS文件是否存在
            if not self.bucket.object_exists(oss_object_key):
                logger.error(f"OSS文件不存在: {oss_object_key}")
                return False
            
            # 确保本地目录存在
            os.makedirs(os.path.dirname(local_file_path), exist_ok=True)
            
            self.bucket.get_object_to_file(oss_object_key, local_file_path)
            
            logger.info(f"文件下载成功: {oss_object_key} -> {local_file_path}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"下载文件时发生错误: {str(e)}")
            return False
    
    def upload_directory(self,
            *, 
            local_directory: str, 
            oss_prefix: str = "",
    ) -> dict:
        """
        上传整个目录到OSS
        
        Args:
            local_directory: 本地目录路径
            oss_prefix: OSS前缀（目录在OSS中的路径）

        Returns:
            dict: 上传结果统计
        """
        if not os.path.exists(local_directory):
            logger.error(f"本地目录不存在: {local_directory}")
            return {"success": 0, "failed": 0, "total": 0}
        
        results = {"success": 0, "failed": 0, "total": 0}
        files_to_upload = []
        
        # 收集所有文件
        for root, dirs, files in os.walk(local_directory):
            for file in files:
                local_path = os.path.join(root, file)
                relative_path = os.path.relpath(local_path, local_directory)
                oss_path = os.path.join(oss_prefix, relative_path).replace('\\', '/')
                files_to_upload.append((local_path, oss_path))
        
        results["total"] = len(files_to_upload)
        
  
        for local_path, oss_path in files_to_upload:
            try:
                if self.upload_file(local_path, oss_path, show_progress=False):
                    results["success"] += 1
                else:
                    results["failed"] += 1
                 
            except Exception as e:
                self.logger.error(f"上传文件失败 {local_path}: {str(e)}")
                results["failed"] += 1

        
        logger.info(f"目录上传完成: 成功 {results['success']}, 失败 {results['failed']}, 总计 {results['total']}")
        return results
    
    # def list_objects(self, prefix: str = "", limit: int = 100) -> List[str]:
    #     """
    #     列出OSS中的对象
        
    #     Args:
    #         prefix: 对象前缀过滤
    #         limit: 最大返回数量
            
    #     Returns:
    #         List[str]: 对象键列表
    #     """
    #     try:
    #         objects = []
    #         for obj in oss2.ObjectIterator(self.bucket, prefix=prefix, max_keys=limit):
    #             objects.append(obj.key)
    #         return objects
    #     except Exception as e:
    #         logger.error(f"列出对象时发生错误: {str(e)}")
    #         return []
    
    
    def object_exists(self, oss_object_key: str) -> bool:
        """
        检查对象是否存在
        
        Args:
            oss_object_key: OSS对象键
            
        Returns:
            bool: 对象是否存在
        """
        try:
            return self.bucket.object_exists(oss_object_key)
        except Exception as e:
            logger.error(f"检查对象存在性时发生错误: {str(e)}")
            return False


def create_oss_client_from_env() -> Optional[OSSClient]:
    """
    从环境变量创建OSS客户端
    
    Returns:
        Optional[OSSClient]: OSS客户端实例，失败返回None
    """
    try:
        access_key_id = os.getenv('OSS_ACCESS_KEY_ID')
        access_key_secret = os.getenv('OSS_ACCESS_KEY_SECRET')
        endpoint = os.getenv('OSS_ENDPOINT')
        bucket_name = os.getenv('OSS_BUCKET_NAME')
        
        if not all([access_key_id, access_key_secret, endpoint, bucket_name]):
            logging.warning("环境变量不完整，无法创建OSS客户端")
            return None
        
        return OSSClient(access_key_id, access_key_secret, endpoint, bucket_name)
    except Exception as e:
        logging.error(f"从环境变量创建OSS客户端失败: {str(e)}")
        return None


# 使用示例
if __name__ == "__main__":
    # 示例配置 - 请替换为您的实际配置
    ACCESS_KEY_ID = "sdf"
    ACCESS_KEY_SECRET = "sdf"
    ENDPOINT = "sdfsdf"
    BUCKET_NAME = "sdfs"
    
    # 创建OSS客户端
    oss_client = OSSClient(ACCESS_KEY_ID, ACCESS_KEY_SECRET, ENDPOINT, BUCKET_NAME)
    
    # 示例1: 上传单个文件
    #oss_url = oss_client.upload_file(local_file_path="D:/test_oss.txt", oss_object_key="oss_folder/test_file.txt")
    
    #print(oss_url)
    
    # 示例2: 下载单个文件
    # oss_client.download_file("oss_folder/file.txt", "downloaded_file.txt")
    
    # 示例3: 上传整个目录
    # oss_client.upload_directory("local_directory", "oss_prefix/")
    
    # 示例4: 列出对象
    # objects = oss_client.list_objects("prefix/")
    # print("OSS中的对象:", objects)
    
    print("OSS客户端创建成功！请配置您的阿里云OSS信息后使用。")