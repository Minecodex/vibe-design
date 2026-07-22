from app.core.providers import PROVIDER_REGISTRY


def test_provider_registry_uses_readable_chinese_labels():
    kling = PROVIDER_REGISTRY["kling"]
    jimeng = PROVIDER_REGISTRY["jimeng"]
    volcark = PROVIDER_REGISTRY["volcark"]

    assert kling["name"] == "可灵"
    assert kling["description"] == "快手开发的新一代AI原生视频生成模型"
    assert kling["models"]["text2image"][0]["label"] == "图片2.1"
    assert kling["models"]["text2video"][0]["label"] == "视频2.6"

    assert jimeng["name"] == "即梦"
    assert jimeng["models"]["text2image"][0]["label"] == "图片生成4.0"
    assert jimeng["models"]["text2video"][0]["label"] == "视频生成3.0pro"

    assert volcark["name"] == "火山方舟"
