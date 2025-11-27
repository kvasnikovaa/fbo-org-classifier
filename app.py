import streamlit as st

from classifier_core import classify_organization


# ---------- Small helpers ----------

def pill_style(score: float) -> str:
    """
    Возвращает inline-CSS для тэга в зависимости от confidence.
    score в диапазоне 0–100.
    """
    if score is None:
        bg = "#f2f2f2"
        color = "#444444"
        border = "#dddddd"
    elif score <= 30:
        # красный — low confidence
        bg = "#ffe5e5"
        color = "#b00020"
        border = "#ffb3b3"
    elif score <= 60:
        # оранжевый — medium
        bg = "#fff4d6"
        color = "#8a5a00"
        border = "#ffd27f"
    else:
        # зелёный — high
        bg = "#e5f6ea"
        color = "#1b5e20"
        border = "#86d19a"

    return (
        f"background-color:{bg}; color:{color}; "
        f"padding:0.35rem 1.0rem; border-radius:999px; "
        f"border:1px solid {border}; font-weight:500; "
        f"font-size:0.9rem; display:inline-block;"
    )


def render_pill(label: str, score: float | None) -> None:
    style = pill_style(score)
    st.markdown(
        f"<span style='{style}'>{label}</span>",
        unsafe_allow_html=True,
    )


def format_confidence(score: float | None) -> str:
    if score is None:
        return "Confidence: N/A"
    return f"Confidence: {score:.0f}%"


# ---------- Page layout ----------

st.set_page_config(
    page_title="FBO Classifier",
    page_icon="🕊️",
    layout="wide",
)

st.title("FBO Classifier")

st.write(
    "Enter an organization name and website URL to automatically detect "
    "its **FBO type**, **primary religion**, and **activity status**."
)

with st.form("input_form"):
    org_name = st.text_input("Organization name", value="")
    url = st.text_input("Website URL (https://…)", value="")
    submitted = st.form_submit_button("Classify")

if submitted and org_name.strip() and url.strip():
    try:
        result = classify_organization(org_name.strip(), url.strip())
    except Exception as e:
        st.error(f"Error while classifying: {e}")
        st.info(
            "Check that the URL is correct, reachable from your network, "
            "and that the site does not block automated requests."
        )
        st.stop()

    fb_type = result.get("type", "Unknown")
    religion = result.get("religion", "Other/Unknown")
    activity = result.get("activity_status", "Unknown")

    conf = result.get("confidence", {}) or {}
    type_conf = conf.get("type")
    rel_conf = conf.get("religion")
    act_conf = conf.get("activity")

    st.markdown("---")
    st.subheader("📄 Classification result")

    col_type, col_rel, col_act = st.columns(3)

    with col_type:
        st.markdown("**Type (FBO segment)**")
        render_pill(fb_type, type_conf)
        st.caption(format_confidence(type_conf))

    with col_rel:
        st.markdown("**Primary religion**")
        render_pill(religion, rel_conf)
        st.caption(format_confidence(rel_conf))

    with col_act:
        st.markdown("**Activity status**")
        render_pill(activity, act_conf)
        st.caption(format_confidence(act_conf))

    with st.expander("Details & scores"):
        st.write("Raw scores (for debugging / tuning):")
        st.json(result.get("scores", {}))
        st.write("Debug info:")
        st.json(result.get("debug", {}))

else:
    st.markdown("---")
    st.info("Fill the fields above and press **Classify** to see the result.")
