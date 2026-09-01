from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    iett_wsdl_url: str | None = "https://api.ibb.gov.tr/iett/FiloDurum/SeferGerceklesme.asmx?wsdl"
    iett_api_username: str | None = None
    iett_api_password: str | None = None
    iett_stops_wsdl_url: str | None = "https://api.ibb.gov.tr/iett/UlasimAnaVeri/HatDurakGuzergah.asmx?wsdl"
    iett_ntc_api_url: str | None = "https://ntcapi.iett.istanbul/service"
    iett_live_url: str | None = None
    iett_request_timeout_seconds: float = 10
    live_cache_seconds: int = 20
    max_vehicle_age_seconds: int = 180

    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")


settings = Settings()
