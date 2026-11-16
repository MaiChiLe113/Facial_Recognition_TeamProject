"""Name -> class registries for stages and features.

    @register_stage("emotion")
    class EmotionStage(Stage): ...

The name is what backend/pipeline.json refers to. Two parts with the same name is an error,
raised when the second module is imported, so a clash shows up straight away.
"""
_STAGES: dict[str, type] = {}
_FEATURES: dict[str, type] = {}


def _register(table, kind, name):
    def decorator(cls):
        if name in table and table[name] is not cls:
            raise ValueError(f"{kind} name '{name}' is already used by {table[name].__module__}.{table[name].__name__}")
        cls.name = name
        table[name] = cls
        return cls
    return decorator


def register_stage(name):
    return _register(_STAGES, "Stage", name)


def register_feature(name):
    return _register(_FEATURES, "Feature", name)


def stage_classes():
    return dict(_STAGES)


def feature_classes():
    return dict(_FEATURES)
