from modules.strategies.compiler import CompiledStrategy


def evaluate_signal(artifact: CompiledStrategy, features: dict):
    return artifact.evaluate(features)
