from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources import PydanticBaseSettingsSource

# ---------------------------------------------------------------------------
# Module-level constants (formerly env-tunable Settings fields)
# These are coupled to code/protocol/brand and must not vary per deployment.
# ---------------------------------------------------------------------------
API_V1_STR = "/api/v1"
JWT_ALGORITHM = "HS256"
APP_TIMEZONE = "Asia/Shanghai"
REDIS_NAMESPACE = "pixel-reorganization"
EVENT_NOTIFICATION_COALESCE_TYPES: frozenset[str] = frozenset(
    {"presentation.block.delta", "tool_call_argument_delta"}
)
LICENSE_CACHE_TTL_SECONDS = 3600

# Debug / pool steady-state defaults
DB_POOL_LOGGING = False
SQLALCHEMY_ECHO = False
DB_POOL_PRE_PING = True
DB_POOL_USE_LIFO = True
DB_POOL_TIMEOUT = 30
DB_POOL_RECYCLE = 1800
HARNESS_CONTEXT_PROJECTION_PERF_LOG_ENABLED = False
HARNESS_CONTEXT_PROJECTION_PERF_LOG_DIR = "work"

# Protocol-layer timeouts / retries (LAN + HTTP client tuning, deployment-invariant)
HARNESS_STREAM_CONNECT_TIMEOUT_SECONDS = 15.0
HARNESS_STREAM_WRITE_TIMEOUT_SECONDS = 120.0
HARNESS_STREAM_POOL_TIMEOUT_SECONDS = 15.0
HARNESS_STREAM_MAX_RETRIES_NO_PROGRESS = 3
HARNESS_STREAM_MAX_RETRIES_TOOL_ARGS_ONLY = 4
APIMART_CONNECT_TIMEOUT_SECONDS = 15.0
APIMART_WRITE_TIMEOUT_SECONDS = 300.0
APIMART_POOL_TIMEOUT_SECONDS = 15.0
APIMART_IMAGE_SUBMIT_MAX_ATTEMPTS = 2
REDIS_CONNECT_TIMEOUT_SECONDS = 2.0
REDIS_OPERATION_TIMEOUT_SECONDS = 5.0
# socket-level read timeout. Must be > REDIS_OPERATION_TIMEOUT_SECONDS so that
# the application-level asyncio.wait_for fires first under normal slow-Redis
# conditions, but a half-open / silently-dropped TCP connection still gets
# evicted before it can stall the event loop indefinitely.
REDIS_SOCKET_TIMEOUT_SECONDS = 10.0
# TCP keepalive lets the kernel detect dead peers (NAT/LB silent drops) and
# eject stale connections from the pool before the next operation.
REDIS_SOCKET_KEEPALIVE = True
REDIS_MAX_PAYLOAD_BYTES = 65536
REDIS_CATALOG_MAX_PAYLOAD_BYTES = 2 * 1024 * 1024
REDIS_HEALTH_CHECK_INTERVAL_SECONDS = 30
PROVIDER_OPERATION_RETRY_DELAY_SECONDS = 1.0
PROVIDER_OPERATION_GENERATION_QUERY_POLL_SECONDS = 3.0
PROVIDER_OPERATION_RETRYABLE_MAX_ATTEMPTS = 6

# Internal queue sizes (per-connection / per-process; do not scale with machine)
SSE_REALTIME_QUEUE_MAX_SIZE = 128
SSE_CONVERSATION_MARKER_QUEUE_MAX_SIZE = 256
SSE_QUEUE_OVERFLOW_LOG_INTERVAL_SECONDS = 30
CONVERSATION_EVENT_SEQUENCE_CACHE_MAX_ENTRIES = 20000
HARNESS_ANALYZE_IMAGE_STREAM_DELTA_FLUSH_INTERVAL_SECONDS = 1.0
HARNESS_ANALYZE_IMAGE_STREAM_DELTA_FLUSH_CHARS = 512
HARNESS_PRESENTATION_DELTA_PERSIST_FLUSH_INTERVAL_SECONDS = 1.0
HARNESS_PRESENTATION_DELTA_PERSIST_MAX_BATCH_SIZE = 200
HARNESS_PRESENTATION_DELTA_PERSIST_QUEUE_MAX_SIZE = 5000
HARNESS_PRESENTATION_DELTA_PERSIST_MAX_MERGED_CHARS = 8192
HARNESS_ACTIVE_RUN_STATE_CACHE_TTL_SECONDS = 2.0
HARNESS_ACTIVE_RUN_STATE_CACHE_MAX_ENTRIES = 10000

# Task scheduling intervals (Redis wakeup is primary signal; polling is fallback)
TASK_POLL_INTERVAL_SECONDS = 3.0
GENERATION_SCHEDULER_IDLE_WAIT_SECONDS = 10.0
PROVIDER_OPERATION_SCHEDULER_IDLE_WAIT_SECONDS = 10.0
GENERATION_TASK_ACTIVE_POLL_SECONDS = 3.0
TASK_POLL_CLAIM_LEASE_SECONDS = 30

_FIXED_ENV_FIELDS = {
    "BUILTIN_PROVIDER_API_KEY",
    "BUILTIN_PROVIDER_CODE",
    "BUILTIN_PROVIDER_BILLING_UNIT_PER_YUAN",
    "LICENSE_ENVELOPE_KEY",
    "DEPLOY_TYPE",
}

_DEFAULT_AGENT_HIDDEN_TOOL_CALLS: tuple[str, ...] = ()


class _FilteredSettingsSource(PydanticBaseSettingsSource):
    def __init__(
        self,
        source: PydanticBaseSettingsSource,
        excluded_fields: set[str],
    ) -> None:
        super().__init__(source.settings_cls)
        self._source = source
        self._excluded_fields = excluded_fields

    def get_field_value(self, field, field_name: str):
        return self._source.get_field_value(field, field_name)

    def __call__(self) -> dict[str, object]:
        self._source._set_current_state(self.current_state)
        self._source._set_settings_sources_data(self.settings_sources_data)
        source_data = self._source()
        return {
            key: value
            for key, value in source_data.items()
            if key not in self._excluded_fields
        }


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    APP_NAME: str = "像素重组"
    APP_NAME_EN: str = "Pixel Reorganization"
    APP_ENV: Literal["development", "staging", "production"] = "development"
    DEPLOY_TYPE: Literal["saas", "private"] = "private"
    DEBUG: bool = False
    UVICORN_ACCESS_LOG_ENABLED: bool = False
    HARNESS_WORKSPACE_ROOT: str = "uploads/harness"
    AVATAR_UPLOAD_MAX_BYTES: int = 5 * 1024 * 1024
    CANVAS_IMAGE_UPLOAD_MAX_BYTES: int = 20 * 1024 * 1024
    CANVAS_VIDEO_UPLOAD_MAX_BYTES: int = 500 * 1024 * 1024
    HARNESS_ATTACHMENT_UPLOAD_MAX_BYTES: int = 50 * 1024 * 1024
    BASE64_IMAGE_COMPRESS_THRESHOLD_BYTES: int = 20 * 1024 * 1024
    BASE64_IMAGE_QUALITY: int = 82
    BASE64_IMAGE_OUTPUT_MAX_BYTES: int = 20 * 1024 * 1024
    MEDIA_DOWNLOAD_MAX_BYTES: int = 200 * 1024 * 1024
    MEDIA_DOWNLOAD_TIMEOUT_SECONDS: float = 180.0
    OFFICE_SESSION_MAX_SOURCE_BYTES: int = 100 * 1024 * 1024
    HARNESS_STORAGE_DATABASE_URL: str = ""
    # Command execution sandbox (bubblewrap). The executor wraps commands in bwrap when
    # the runtime supports it and degrades to a plain spawn otherwise; there is no longer
    # a local/docker backend switch.
    HARNESS_SANDBOX_ENABLED: bool = True
    HARNESS_SANDBOX_AUTO_ALLOW: bool = True  # mirrors claude-code autoAllowBashIfSandboxed
    HARNESS_SANDBOX_BWRAP_PATH: str = ""  # optional explicit path to the bwrap binary
    SEARCH_PROVIDER: str = "duckduckgo"
    SEARCH_TIMEOUT_SECONDS: int = 8
    SEARCH_MAX_RESULTS: int = 10
    DUCKDUCKGO_REGION: str = "cn-zh"
    DUCKDUCKGO_SAFESEARCH: str = "moderate"
    DUCKDUCKGO_TIME_LIMIT: str = ""
    DUCKDUCKGO_BACKEND: str = "auto"

    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Comma-separated origins like "http://localhost:5173,http://localhost:3000"
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    # Comma-separated tool names whose calls are hidden from the agent UI. Empty by
    # default (all tool calls render as Claude-Code-style rows); set this to suppress
    # specific internal/bookkeeping tools, e.g. "lc_read_skill_file".
    AGENT_HIDDEN_TOOL_CALLS: str = ""

    @property
    def agent_hidden_tool_calls(self) -> list[str]:
        names: list[str] = list(_DEFAULT_AGENT_HIDDEN_TOOL_CALLS)
        for part in str(self.AGENT_HIDDEN_TOOL_CALLS or "").split(","):
            name = part.strip()
            if name and name not in names:
                names.append(name)
        return names

    BUILTIN_PROVIDER_CODE: Literal["apimart", "lingyaai"] = "apimart"
    # Deprecated compatibility field. Runtime requests never read this value;
    # APIMart credentials are resolved per user from the database.
    BUILTIN_PROVIDER_API_KEY: str = ""
    BUILTIN_PROVIDER_BILLING_UNIT_PER_YUAN: int = 500000
    LINGYAAI_BASE_URL: str = "https://lyapi.com"
    # APIMart is the balance source of truth. The enabled field remains only so
    # older deployment files continue to parse; runtime no longer branches on it.
    PROVIDER_BALANCE_SYNC_ENABLED: bool = True
    PROVIDER_BALANCE_SYNC_INTERVAL_SECONDS: float = 300.0
    PROVIDER_BALANCE_SYNC_SNAPSHOT_TTL_SECONDS: int = 900
    PROVIDER_BALANCE_SYNC_BATCH_SIZE: int = 100
    PROVIDER_BALANCE_SYNC_MAX_CONCURRENCY: int = 5
    PROVIDER_RATE_LIMIT_GENERATION_SUBMIT_LIMIT: int = 120
    PROVIDER_RATE_LIMIT_GENERATION_SUBMIT_WINDOW_SECONDS: int = 60
    PROVIDER_RATE_LIMIT_GENERATION_QUERY_LIMIT: int = 600
    PROVIDER_RATE_LIMIT_GENERATION_QUERY_WINDOW_SECONDS: int = 60
    PROVIDER_RATE_LIMIT_RESULT_DOWNLOAD_LIMIT: int = 300
    PROVIDER_RATE_LIMIT_RESULT_DOWNLOAD_WINDOW_SECONDS: int = 60
    PROVIDER_RATE_LIMIT_BALANCE_FETCH_LIMIT: int = 1
    PROVIDER_RATE_LIMIT_BALANCE_FETCH_WINDOW_SECONDS: int = 300
    PROVIDER_RATE_LIMIT_BILLING_FETCH_LIMIT: int = 9
    PROVIDER_RATE_LIMIT_BILLING_FETCH_WINDOW_SECONDS: int = 60
    LINGYAAI_BILLING_RECONCILE_INTERVAL_SECONDS: float = 1.0
    LINGYAAI_BILLING_RECONCILE_BATCH_SIZE: int = 50
    LINGYAAI_BILLING_RECONCILE_LOCK_SECONDS: int = 30
    LINGYAAI_BILLING_FAST_RETRY_SECONDS: int = 60
    LINGYAAI_BILLING_FAST_RETRY_DELAY_SECONDS: int = 1
    LINGYAAI_BILLING_NORMAL_RETRY_DELAY_SECONDS: int = 5
    LINGYAAI_BILLING_SLOW_RETRY_DELAY_SECONDS: int = 30
    LINGYAAI_BILLING_MANUAL_REVIEW_AFTER_SECONDS: int = 900
    APIMART_TIMEOUT_SECONDS: float = 120.0
    HARNESS_MODEL_TURN_TIMEOUT_SECONDS: float = 600.0
    CLASSIFIER_TIMEOUT_SECONDS: float = 5.0
    HARNESS_STREAM_READ_TIMEOUT_SECONDS: float = 720.0
    HARNESS_RECALL_SIDECAR_WORKER_ENABLED: bool = False
    HARNESS_RECALL_SIDECAR_WORKER_INTERVAL_SECONDS: float = 5.0
    HARNESS_RECALL_SIDECAR_WORKER_LEASE_SECONDS: int = 60
    HARNESS_RECALL_SIDECAR_WORKER_BATCH_SIZE: int = 1
    HARNESS_RECALL_SIDECAR_WORKER_MAX_CONCURRENCY: int = 1
    HARNESS_AUTOCOMPACT_PCT_OVERRIDE: str | None = None
    HARNESS_DISABLE_AUTO_COMPACT: bool = False
    HARNESS_PROMPT_CACHE_DEBUG: bool = False
    HARNESS_PROMPT_CACHE_DEBUG_FULL: bool = False
    HARNESS_AGENT_MAX_ACTIVE_RUNS: int = 8
    HARNESS_WORKFLOW_MAX_ACTIVE_STEPS: int = 8
    HARNESS_BLOCKING_IO_WORKERS: int = 6
    HARNESS_TOOL_BATCH_MAX_CONCURRENCY: int = 10
    HARNESS_PRESENTATION_DELTA_ASYNC_PERSIST_ENABLED: bool = True
    HARNESS_MEDIA_BARRIER_RECENT_TOOL_WINDOW: int = 5
    ECOMMERCE_PRODUCT_IMAGE_CONTEXT_TEMPLATE: str = (
        "你需要参考上面实拍图图片分析内容，实拍图和对应的基准生成对应的图片\n\n"
        "{图片分类提示词}\n\n"
        "{图片风格提示词}\n\n"
        "{平台规则提示词}\n\n"
        "{人物参考图提示词}\n"
        "{人物参考图}\n\n"
        "{背景参考图提示词}\n"
        "{背景参考图}\n\n"
        "{其他商品主图参考图提示词}\n"
        "{其他商品参考图}\n\n"
        "{负面约束提示词}\n\n"
        "生成商品图数量：{生成商品图数量}\n\n"
        "{用户需求}"
    )
    ECOMMERCE_PRODUCT_IMAGE_PLATFORM_RULE_PROMPT: str = (
        "【平台规则】\n"
        "适合国内电商男装主图。主商品必须清楚完整，画面要有点击吸引力和转化价值。\n"
        "允许合理内搭、配件和道具强化穿搭联想，但不能误导买家以为内搭、配件或道具一定随商品售卖。主商品必须最大、最清楚、视觉权重最高。\n"
        "不添加文字、水印、边框、价格、促销角标、平台标签、销量、排名、最低价、官方认证、证书或虚假卖点。商品真实一致优先于风格氛围。"
    )
    ECOMMERCE_PRODUCT_IMAGE_BACKGROUND_REFERENCE_PROMPT: str = (
        "【背景参考图】\n"
        "仅参考背景图的场景结构、透视、光线、色调、景深、材质、道具位置与整体氛围，背景布局尽量高保真还原；不参考其中服装和人物，不新增文字、品牌、路人正脸或其他元素；背景真实、干净、高级，用于衬托主商品，主商品仍以商品锁定卡为准。"
    )
    ECOMMERCE_PRODUCT_IMAGE_MODEL_REFERENCE_PROMPT: str = (
        "【人物参考】\n"
        "仅参考模特的身材比例、镜头感和气质，不参考其服装与背景；用该模特自然穿搭主商品，搭配合理、比例协调，重点凸显主商品的版型、颜色、质感和细节，不遮挡关键卖点，画面真实高级、无AI感。"
    )
    ECOMMERCE_PRODUCT_IMAGE_OTHER_MAIN_IMAGE_REFERENCE_PROMPT: str = (
        "【其他主图参考提示词】\n"
        "仅参考参考图的主图风格、构图、背景、人物姿态、镜头角度、光影与氛围，不参考其服装商品本身；若含人物，仅学习身材比例、动作和气质，不复制脸部、服装和品牌元素；用主商品生成相似风格的电商主图，主商品真实一致、清晰突出、自然高级、无AI感。"
    )
    ECOMMERCE_PRODUCT_IMAGE_NEGATIVE_PROMPT: str = (
        "【通用负面约束】\n"
        "不要失真、不要变形、不要拉伸、不要比例错误、不要透视错误、不要结构错位、不要左右翻转错误、不要穿模、不要面料和纹理失真、不要颜色偏移、不要版型改变、不要领型/袖型/门襟/口袋/纽扣/拉链/拼接/下摆/标签/织标错误、不要凭空新增或删除真实细节。\n\n"
        "不要搭配混乱、不要颜色冲突、不要风格冲突、不要道具堆砌、不要配饰抢主体、不要内搭外搭关系错误、不要背景喧宾夺主、不要让人物或道具盖住商品关键卖点。\n\n"
        "不要主次混乱、不要主体太小、不要裁切关键部位、不要多主体并列、不要九宫格、不要拼图、不要海报化过强。\n\n"
        "不要直接复制参考图中的服装、人物、背景、道具、文字、品牌元素和构图细节，不要让参考图替代主商品，只能参考其风格、氛围、光影和布局逻辑。\n\n"
        "不要低清、模糊、噪点、过曝、死黑、重滤镜、AI感、塑料感、过度磨皮、毛边、抠图溢色、文字乱码、水印、边框、价格牌、促销字、二维码、虚假品牌标识、侵权元素、路人正脸、可识别身份。\n\n"
        "【最终输出】\n"
        "输出 4-6 张独立的高级男装【分类+风格】主图候选。\n"
        "每张图都必须展示同一件主商品，但通过不同内搭、配件、道具、背景氛围和摆放方式呈现不同转化角度。\n"
        "主商品必须真实一致、完整清楚、细节可信。\n"
        "允许基础内搭、自然打开门襟、合理褶皱和年轻化边缘道具来提升点击和转化，但不得改变、遮挡或替换主商品。\n"
        "不要拼图，不要九宫格，不要编号，不要在图片上添加文字。"
    )
    HARNESS_WORKFLOW_DIAGNOSTICS_ENABLED: bool = False
    HARNESS_ACTIVITY_DIAGNOSTICS_ENABLED: bool = False
    HARNESS_ASYNCIO_DIAGNOSTICS_ENABLED: bool = False
    HARNESS_ASYNCIO_SLOW_CALLBACK_SECONDS: float = 5.0
    HARNESS_ASYNCIO_LAG_THRESHOLD_SECONDS: float = 5.0
    HARNESS_ASYNCIO_LAG_INTERVAL_SECONDS: float = 0.5
    HARNESS_TOOL_LOOP_DIAGNOSTICS_ENABLED: bool = False
    HARNESS_CRITIQUE_ENABLED: bool = True
    HARNESS_CRITIQUE_MAX_ROUNDS: int = 3
    HARNESS_CRITIQUE_SCORE_SCALE: int = 10
    HARNESS_CRITIQUE_SCORE_THRESHOLD: float = 8.0
    HARNESS_CRITIQUE_FALLBACK_POLICY: str = "ship_best"
    HARNESS_CRITIQUE_PER_ROUND_TIMEOUT_SECONDS: float = 90.0
    HARNESS_CRITIQUE_TOTAL_TIMEOUT_SECONDS: float = 240.0
    HARNESS_CRITIQUE_PARSER_MAX_BLOCK_BYTES: int = 262_144
    HARNESS_WORKFLOW_TOOL_FAILURE_BREAKER_THRESHOLD: int = 3
    HARNESS_PERF_SEGMENT_WARNING_SECONDS: float = 0.1
    HARNESS_WORKFLOW_STEP_WARNING_SECONDS: float = 10.0
    HARNESS_ACTIVITY_WARNING_SECONDS: float = 10.0
    HARNESS_LEASE_SAFETY_WARNING_SECONDS: float = 30.0
    HARNESS_AGENT_CONTEXT_CONCURRENCY: int = 1
    HARNESS_RESOURCE_LLM_CONCURRENCY: int = 16
    HARNESS_RESOURCE_FILE_IO_CONCURRENCY: int = 10
    HARNESS_RESOURCE_CPU_TOOL_CONCURRENCY: int = 4
    HARNESS_RESOURCE_SUBPROCESS_CONCURRENCY: int = 8
    HARNESS_RESOURCE_BROWSER_CONCURRENCY: int = 2
    HARNESS_RESOURCE_OFFICE_CONCURRENCY: int = 1
    HARNESS_RESOURCE_NETWORK_CONCURRENCY: int = 16
    OLLAMA_MULTIMODAL_ENABLED: bool = False
    OLLAMA_BASE_URL: str = "http://localhost:11434/v1"
    OLLAMA_API_KEY: str = "ollama"
    OLLAMA_IMAGE_API_KEY: str = ""
    OLLAMA_MULTIMODAL_MODEL: str = "gemma4:e4b"
    OLLAMA_MAX_INPUT_TOKENS: int = 0
    OLLAMA_MAX_OUTPUT_TOKENS: int = 0
    OLLAMA_TOOL_CHOICE_FORMAT: Literal["openai", "flat"] = "openai"
    OLLAMA_IMAGE_ANALYSIS_ENABLED: bool = False
    OLLAMA_IMAGE_GENERATION_ENABLED: bool = False
    OLLAMA_IMAGE_GENERATION_MODEL: str = ""
    OLLAMA_IMAGE_GENERATION_CONFIG: str = ""

    REDEMPTION_PUBLIC_KEY: str = ""
    LICENSE_ENVELOPE_KEY: str = ""
    REDIS_ENABLED: bool = True
    REDIS_REQUIRED: bool = True
    REDIS_URL: str = "redis://redis:6379/0"
    REDIS_MAX_CONNECTIONS: int = 64
    REDIS_CONNECT_TIMEOUT_SECONDS: float = REDIS_CONNECT_TIMEOUT_SECONDS
    REDIS_OPERATION_TIMEOUT_SECONDS: float = REDIS_OPERATION_TIMEOUT_SECONDS
    REDIS_SOCKET_TIMEOUT_SECONDS: float = REDIS_SOCKET_TIMEOUT_SECONDS
    REDIS_SOCKET_KEEPALIVE: bool = REDIS_SOCKET_KEEPALIVE
    REDIS_MAX_PAYLOAD_BYTES: int = REDIS_MAX_PAYLOAD_BYTES
    REDIS_CATALOG_MAX_PAYLOAD_BYTES: int = REDIS_CATALOG_MAX_PAYLOAD_BYTES
    REDIS_HEALTH_CHECK_INTERVAL_SECONDS: int = REDIS_HEALTH_CHECK_INTERVAL_SECONDS
    AGENT_CATALOG_CACHE_TTL_SECONDS: int = 24 * 60 * 60
    AGENT_CATALOG_READY_WAIT_SECONDS: float = 60.0
    EVENT_NOTIFICATION_COALESCE_ENABLED: bool = True
    EVENT_NOTIFICATION_COALESCE_WINDOW_MS: int = 50

    TOS_AK: str = ""
    TOS_SK: str = ""
    TOS_ENDPOINT: str = ""
    TOS_REGION: str = ""
    TOS_BUCKET_NAME: str = ""
    TOS_PUBLIC_BASE_URL: str = ""
    TOS_OBJECT_PREFIX: str = "generation-refs/"

    TASK_TIMEOUT_IMAGE_SECONDS: int = 1800
    TASK_TIMEOUT_VIDEO_SECONDS: int = 18000
    OFFICE_SESSION_TTL_SECONDS: int = 24 * 60 * 60
    WEB_CONCURRENCY: int = 6

    DATABASE_URL: str = "sqlite+aiosqlite:///./dev.db"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 10

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        filtered_env_settings = _FilteredSettingsSource(env_settings, _FIXED_ENV_FIELDS)
        filtered_dotenv_settings = _FilteredSettingsSource(dotenv_settings, _FIXED_ENV_FIELDS)
        return (
            init_settings,
            filtered_env_settings,
            filtered_dotenv_settings,
            file_secret_settings,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
