from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, Response  # 添加 Response 导入
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import boto3
import base64
import json
from botocore.config import Config
import os
from typing import Optional
from urllib.parse import quote

app = FastAPI(
    title="合同条款偏离对比服务",
    description="使用方法: 上传标准合同和客户合同进行对比分析，并下载比对结果进行查看",
    version="1.0.0"
)

# AWS配置
config = Config(
    connect_timeout=10, 
    read_timeout=180,
    retries={'max_attempts': 3})
        
# 添加CORS支持
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ComparisonResponse(BaseModel):
    message: str
    status: str
    s3path: Optional[str] = None


@app.post("/upload",
    summary="合同文件对比接口",
    response_model=ComparisonResponse
)
async def upload_files(
    standard_file: UploadFile = File(..., description="标准合同文件"),
    customer_file: UploadFile = File(..., description="客户合同文件")
):
    try:
        # 读取并编码文件
        standard_content = await standard_file.read()
        customer_content = await customer_file.read()
        
        standard_base64 = base64.b64encode(standard_content).decode('utf-8')
        customer_base64 = base64.b64encode(customer_content).decode('utf-8')
        
        # AWS配置
        config = Config(
            connect_timeout=10, 
            read_timeout=180,
            retries={'max_attempts': 3}
        )
        
        # 创建Lambda客户端
        client = boto3.client('lambda',config=config,region_name='cn-northwest-1',aws_access_key_id='******',aws_secret_access_key='******')


        # Lambda参数
        lambda_payload = {
            'standard_contract_file_base64': standard_base64,
            'customer_contract_file_base64': customer_base64
        }

        # 调用Lambda
        response = client.invoke(
            FunctionName='llm_contract_items_comparison_deviate_project',
            InvocationType='RequestResponse',
            Payload=json.dumps(lambda_payload)
        )

        # 处理响应 - 修改这部分代码
        if response['StatusCode'] == 200:
            # 读取响应内容
            response_payload = response['Payload'].read()
            # 解析JSON字符串
            response_data = json.loads(response_payload)
            
            # 检查响应格式
            if isinstance(response_data, dict) and 'body' in response_data:
                # 如果body是字符串，需要再次解析
                if isinstance(response_data['body'], str):
                    body = json.loads(response_data['body'])
                else:
                    body = response_data['body']
                
                s3path = body.get('s3path')
                if s3path:
                    return ComparisonResponse(
                        message="合同对比分析完成",
                        status="success",
                        s3path=s3path
                    )
                else:
                    raise HTTPException(
                        status_code=500,
                        detail="响应中未找到s3path"
                    )
            else:
                # 打印响应内容以便调试
                print("Lambda响应内容:", response_data)
                raise HTTPException(
                    status_code=500,
                    detail="无效的响应格式"
                )
        else:
            raise HTTPException(
                status_code=500,
                detail="Lambda函数调用失败"
            )

    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=500,
            detail=f"JSON解析错误: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"处理过程中发生错误: {str(e)}"
        )

@app.get("/download/{s3path:path}")
async def download_result(s3path: str):
    try:
        # 创建S3客户端
        s3_client = boto3.client('s3',config=config,region_name='cn-northwest-1',aws_access_key_id='*****',aws_secret_access_key='*****')


        # 处理S3路径
        if s3path.startswith('s3://'):
            # 移除 's3://' 前缀
            s3path = s3path[5:]
            
        # 提取bucket和key
        parts = s3path.split('/', 1)
        bucket = parts[0]  # sagemaker-cn-northwest-1-262349763237
        key = parts[1]     # LLM-RAG/workshop/marker/contract_compare_result/202503041528_customer_合同条款偏离结果.html
        
        try:
            # 从S3下载文件
            response = s3_client.get_object(Bucket=bucket, Key=key)
            content = response['Body'].read()
            
            # 从路径中提取文件名
            filename = key.split('/')[-1]
            encoded_filename = quote(filename)  # URL编码文件名
            
            # 返回文件内容
            return Response(
                content=content,
                media_type='text/html',
                headers={
                    "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
                }
            )
        except s3_client.exceptions.NoSuchKey:
            raise HTTPException(status_code=404, detail="文件不存在")
        except s3_client.exceptions.NoSuchBucket:
            raise HTTPException(status_code=404, detail="存储桶不存在")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"下载失败: {str(e)}")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")
        
        
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        reload=False  # 移除 reload 选项
    )
