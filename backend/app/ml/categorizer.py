"""Определение категории по описанию операции. Две модели для A/B-сравнения.

A — TF-IDF и логистическая регрессия (scikit-learn).
B — небольшая нейросеть на PyTorch.

Модели учатся отдельно для каждого пространства: категории у всех свои.
"""

import io
import zlib
from collections import Counter
from dataclasses import dataclass

import joblib
import numpy as np
import torch
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline, make_pipeline
from torch import nn

MIN_SAMPLES = 20
MIN_PER_CLASS = 3
VARIANT_SKLEARN = "A"
VARIANT_TORCH = "B"

_BUCKETS = 2**14
_EMBEDDING_SIZE = 48
_EPOCHS = 60
_SEED = 42


@dataclass(frozen=True)
class TrainingSet:
    texts: list[str]
    labels: list[int]


@dataclass(frozen=True)
class Trained:
    payload: bytes
    accuracy: float
    samples: int
    classes: int


def prepare(texts: list[str], labels: list[int]) -> TrainingSet | None:
    """Убирает редкие категории. None — данных пока мало, модель была бы случайной."""
    counts = Counter(labels)
    pairs = [(t, l) for t, l in zip(texts, labels, strict=True) if counts[l] >= MIN_PER_CLASS]
    if len(pairs) < MIN_SAMPLES or len({label for _, label in pairs}) < 2:
        return None
    kept_texts, kept_labels = zip(*pairs, strict=True)
    return TrainingSet(list(kept_texts), list(kept_labels))


def _split(data: TrainingSet) -> tuple[list[str], list[str], list[int], list[int]]:
    # stratify: в проверочной части должны быть все категории в тех же долях.
    # Одинаковые описания попадают в обе части намеренно: в жизни покупки тоже повторяются,
    # но поэтому точность показывает узнавание знакомого, а не понимание нового
    return train_test_split(
        data.texts, data.labels, test_size=0.25, stratify=data.labels, random_state=_SEED
    )


# --- A: scikit-learn ---


def _sklearn_pipeline() -> Pipeline:
    return make_pipeline(
        # Буквосочетания, а не слова: «Пятёрочка 1234» и «ПЯТЕРОЧКА» окажутся близкими
        TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), sublinear_tf=True),
        LogisticRegression(max_iter=1000, C=10.0),
    )


def train_sklearn(data: TrainingSet) -> Trained:
    train_x, test_x, train_y, test_y = _split(data)
    accuracy = accuracy_score(test_y, _sklearn_pipeline().fit(train_x, train_y).predict(test_x))
    # На проверке точность измерена — итоговая модель учится уже на всех данных
    final = _sklearn_pipeline().fit(data.texts, data.labels)
    buffer = io.BytesIO()
    joblib.dump(final, buffer)
    return Trained(buffer.getvalue(), float(accuracy), len(data.texts), len(set(data.labels)))


def _predict_sklearn(payload: bytes):
    # joblib исполняет код при загрузке, поэтому payload берём только из своей БД
    model: Pipeline = joblib.load(io.BytesIO(payload))

    def predict(texts: list[str]) -> list[tuple[int, float]]:
        probabilities = model.predict_proba(texts)
        best = probabilities.argmax(axis=1)
        return [
            (int(model.classes_[index]), float(row[index]))
            for index, row in zip(best, probabilities, strict=True)
        ]

    return predict


# --- B: PyTorch ---


class _BagClassifier(nn.Module):
    def __init__(self, classes: int) -> None:
        super().__init__()
        self.embedding = nn.EmbeddingBag(_BUCKETS, _EMBEDDING_SIZE, mode="mean")
        self.output = nn.Linear(_EMBEDDING_SIZE, classes)

    def forward(self, tokens: torch.Tensor, offsets: torch.Tensor) -> torch.Tensor:
        return self.output(self.embedding(tokens, offsets))


def _tokens(text: str) -> list[int]:
    value = f" {text.casefold()} "
    # crc32, а не hash(): встроенный hash меняется при каждом запуске Python
    grams = [value[i : i + 3] for i in range(max(len(value) - 2, 1))]
    return [zlib.crc32(gram.encode()) % _BUCKETS for gram in grams]


def _batch(texts: list[str]) -> tuple[torch.Tensor, torch.Tensor]:
    tokens = [_tokens(text) for text in texts]
    offsets = np.cumsum([0, *[len(item) for item in tokens[:-1]]])
    flat = [token for item in tokens for token in item]
    return torch.tensor(flat, dtype=torch.long), torch.tensor(offsets, dtype=torch.long)


def _fit_torch(texts: list[str], targets: list[int], classes: int) -> _BagClassifier:
    torch.manual_seed(_SEED)
    model = _BagClassifier(classes)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.05)
    loss_fn = nn.CrossEntropyLoss()
    tokens, offsets = _batch(texts)
    answer = torch.tensor(targets, dtype=torch.long)
    model.train()
    for _ in range(_EPOCHS):
        optimizer.zero_grad()
        loss_fn(model(tokens, offsets), answer).backward()
        optimizer.step()
    return model.eval()


def train_torch(data: TrainingSet) -> Trained:
    torch.set_num_threads(1)  # модели маленькие, а процессор сервера нужен и остальным
    classes = sorted(set(data.labels))
    index = {label: position for position, label in enumerate(classes)}
    train_x, test_x, train_y, test_y = _split(data)
    model = _fit_torch(train_x, [index[label] for label in train_y], len(classes))
    with torch.no_grad():
        predicted = model(*_batch(test_x)).argmax(dim=1).tolist()
    accuracy = accuracy_score([index[label] for label in test_y], predicted)

    final = _fit_torch(data.texts, [index[label] for label in data.labels], len(classes))
    buffer = io.BytesIO()
    torch.save({"state": final.state_dict(), "classes": classes}, buffer)
    return Trained(buffer.getvalue(), float(accuracy), len(data.texts), len(classes))


def _predict_torch(payload: bytes):
    # weights_only: загружаются только тензоры и числа, исполнить код через файл нельзя
    saved = torch.load(io.BytesIO(payload), weights_only=True)
    classes: list[int] = saved["classes"]
    model = _BagClassifier(len(classes))
    model.load_state_dict(saved["state"])
    model.eval()

    def predict(texts: list[str]) -> list[tuple[int, float]]:
        with torch.no_grad():
            probabilities = torch.softmax(model(*_batch(texts)), dim=1)
        values, positions = probabilities.max(dim=1)
        return [
            (classes[position], float(value))
            for value, position in zip(values.tolist(), positions.tolist(), strict=True)
        ]

    return predict


TRAINERS = {VARIANT_SKLEARN: train_sklearn, VARIANT_TORCH: train_torch}
_LOADERS = {VARIANT_SKLEARN: _predict_sklearn, VARIANT_TORCH: _predict_torch}


def load(variant: str, payload: bytes):
    return _LOADERS[variant](payload)
