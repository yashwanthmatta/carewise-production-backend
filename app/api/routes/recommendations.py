from fastapi import APIRouter, Depends

from app.core.rbac import Role, require_roles
from app.core.security import CurrentUser
from app.schemas.carewise import RecommendationOut, RecommendationRequest

router = APIRouter()


@router.post("/ai", response_model=RecommendationOut)
def create_ai_recommendation(
    payload: RecommendationRequest,
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.CLINICIAN, Role.ADMIN)),
):
    diet_style = payload.diet_style.replace("_", " ")
    diet = [
        f"Use a {diet_style} pattern built around vegetables, protein, fiber-rich carbohydrates, and healthy fats.",
        "Keep sodium, added sugar, and ultra-processed foods limited unless a clinician gives different guidance.",
        "Plan simple repeatable meals for busy days: bowls, soups, wraps, prepared proteins, and washed produce.",
    ]
    habits = [
        "Track symptoms, meals, sleep, movement, and medication timing.",
        "Start with 10 to 20 minutes of gentle movement if safe and increase gradually.",
        "Prepare a doctor-visit summary before appointments.",
    ]
    if "diabetes" in payload.context_text.lower():
        diet.append("For blood sugar support, pair carbohydrates with protein/fiber and avoid skipping meals.")
    if "blood pressure" in payload.context_text.lower() or "hypertension" in payload.context_text.lower():
        diet.append("For blood pressure support, ask a clinician about sodium and potassium targets.")
    return RecommendationOut(
        patient_id=payload.patient_id,
        diet=diet,
        habits=habits,
        safety_notes=[
            "This is education, not diagnosis or treatment.",
            "High-risk symptoms, pregnancy, kidney disease, eating disorders, allergies, or medication changes require clinician review.",
        ],
    )
