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
    Alibaba Cloud OSS client, supporting file upload and download
    """
    
    def __init__(self, 
        access_key_id: str, 
        access_key_secret: str, 
        endpoint: str, 
        bucket_name: str
    ):
        """
        Initialize the OSS client

        Args:
            access_key_id: Alibaba Cloud access key ID
            access_key_secret: Alibaba Cloud access key Secret
            endpoint: OSS endpoint
            bucket_name: Bucket name
        """
        self.access_key_id = access_key_id
        self.access_key_secret = access_key_secret
        self.endpoint = endpoint
        self.bucket_name = bucket_name

        # Create the authentication object
        self.auth = oss2.Auth(access_key_id, access_key_secret)

        # Create the Bucket object
        self.bucket = oss2.Bucket(self.auth, endpoint, bucket_name)


    def upload_file(self,
            * ,
            local_file_path: str, 
            oss_object_key: str,
            expires:int = 3600*24*7 
        ) -> str:
        """
        Upload a file to OSS

        Args:
            local_file_path: Local file path
            oss_object_key: OSS object key (the file's path in OSS)
        Returns:
            str: The oss_url corresponding to the file
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
        Upload a file to OSS

        Args:
            data:  File binary data
            oss_object_key: OSS object key (the file's path in OSS)
        Returns:
            str: The oss_url corresponding to the file
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
        Download a file from OSS

        Args:
            oss_object_key: OSS object key (the file's path in OSS)
            local_file_path: Local path to save the file

        Returns:
            bool: Whether the download succeeded
        """
        try:
            # Check whether the OSS file exists
            if not self.bucket.object_exists(oss_object_key):
                logger.error(f"OSS文件不存在: {oss_object_key}")
                return False

            # Ensure the local directory exists
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
        Upload an entire directory to OSS

        Args:
            local_directory: Local directory path
            oss_prefix: OSS prefix (the directory's path in OSS)

        Returns:
            dict: Upload result statistics
        """
        if not os.path.exists(local_directory):
            logger.error(f"本地目录不存在: {local_directory}")
            return {"success": 0, "failed": 0, "total": 0}

        results = {"success": 0, "failed": 0, "total": 0}
        files_to_upload = []

        # Collect all files
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
    #     List objects in OSS

    #     Args:
    #         prefix: Object prefix filter
    #         limit: Maximum number to return

    #     Returns:
    #         List[str]: List of object keys
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
        Check whether an object exists

        Args:
            oss_object_key: OSS object key

        Returns:
            bool: Whether the object exists
        """
        try:
            return self.bucket.object_exists(oss_object_key)
        except Exception as e:
            logger.error(f"检查对象存在性时发生错误: {str(e)}")
            return False


def create_oss_client_from_env() -> Optional[OSSClient]:
    """
    Create an OSS client from environment variables

    Returns:
        Optional[OSSClient]: OSS client instance, or None on failure
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


# Usage example
if __name__ == "__main__":
    # Example configuration - please replace with your actual configuration
    ACCESS_KEY_ID = "sdf"
    ACCESS_KEY_SECRET = "sdf"
    ENDPOINT = "sdfsdf"
    BUCKET_NAME = "sdfs"

    # Create the OSS client
    oss_client = OSSClient(ACCESS_KEY_ID, ACCESS_KEY_SECRET, ENDPOINT, BUCKET_NAME)

    # Example 1: upload a single file
    #oss_url = oss_client.upload_file(local_file_path="D:/test_oss.txt", oss_object_key="oss_folder/test_file.txt")

    #print(oss_url)

    # Example 2: download a single file
    # oss_client.download_file("oss_folder/file.txt", "downloaded_file.txt")

    # Example 3: upload an entire directory
    # oss_client.upload_directory("local_directory", "oss_prefix/")

    # Example 4: list objects
    # objects = oss_client.list_objects("prefix/")
    # print("OSS中的对象:", objects)

    print("OSS客户端创建成功！请配置您的阿里云OSS信息后使用。")