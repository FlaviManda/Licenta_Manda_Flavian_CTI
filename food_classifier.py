import torch
from torchvision import models, transforms
from PIL import Image
import base64
import io
import os
import json

MODEL_PATH = r"C:\Users\manda\CalorieVisor\weights\custom_food_resnet18.pth"

# Load class names from JSON
with open(r"C:\Users\manda\CalorieVisor\weights\custom_food_class_names.json", "r") as f:
    CLASS_NAMES = json.load(f)
print("Loaded class names:", CLASS_NAMES)

NUM_CLASSES = len(CLASS_NAMES)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

_model = None

def load_model():
    model = models.resnet18(pretrained=False)
    model.fc = torch.nn.Linear(model.fc.in_features, NUM_CLASSES)
    model.load_state_dict(torch.load(MODEL_PATH, map_location=device))
    model = model.to(device)
    model.eval()
    return model

def get_model():
    global _model
    if _model is None:
        _model = load_model()
    return _model

def predict_food_label(image: Image.Image) -> str:
    model = get_model()
    preprocess = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])
    input_tensor = preprocess(image).unsqueeze(0).to(device)
    with torch.no_grad():
        outputs = model(input_tensor)
        probs = torch.nn.functional.softmax(outputs, dim=1)
        top3_prob, top3_idx = torch.topk(probs, 3)
        print("Model output:", outputs)
        print("Top3 indices:", top3_idx)
        print("Top3 labels:", [CLASS_NAMES[i] for i in top3_idx[0].tolist()])
        predictions = []
        for prob, idx in zip(top3_prob[0], top3_idx[0]):
            label = CLASS_NAMES[idx.item()]
            predictions.append(f"{label} ({prob.item():.2%})")
        return " | ".join(predictions)

def predict_from_path(image_path):
    image = Image.open(image_path).convert('RGB')
    return predict_food_label(image)

def predict_from_base64(image_base64):
    if ',' in image_base64:
        header, encoded = image_base64.split(',', 1)
    else:
        encoded = image_base64
    image_data = base64.b64decode(encoded)
    image = Image.open(io.BytesIO(image_data)).convert('RGB')
    return predict_food_label(image) 