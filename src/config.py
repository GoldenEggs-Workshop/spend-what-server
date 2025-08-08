from pydantic import BaseModel, Field


class Config(BaseModel):
    mongodb_url: str = Field(..., title="MongoDB URL", description="The URL for connecting to MongoDB")
    mongodb_db: str = Field(..., title="MongoDB Database Name", description="The name of the MongoDB database")
    mongodb_username: str = Field(..., title="MongoDB Username", description="Username for MongoDB authentication")
    mongodb_password: str = Field(..., title="MongoDB Password", description="Password for MongoDB authentication")
    secret_key: str = Field(..., title="Secret Key", description="Secret key for signing tokens and cookies")
