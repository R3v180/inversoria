import streamlit as st
import time
from i18n import _

def render_onboarding():
    db = st.session_state.db
    
    st.markdown("""
        <style>
        .onboarding-container {
            max-width: 800px;
            margin: 0 auto;
            padding: 2rem;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 15px;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        </style>
    """, unsafe_allow_html=True)

    with st.container():
        st.markdown(f"<h1 style='text-align: center;'>🏛️ { _('WELCOME_TITLE') }</h1>", unsafe_allow_html=True)
        st.markdown(f"<p style='text-align: center; color: #888;'>{ _('WELCOME_SUBTITLE') }</p>", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        # Usamos pestañas para simular los pasos del tutorial/onboarding
        tab1, tab2, tab3 = st.tabs(["👤 Identity", "🛡️ Strategy", "📖 Tutorial"])

        with tab1:
            st.markdown("### Paso 1: Identidad e Idioma")
            name = st.text_input(_('USER_NAME_LABEL'), placeholder="Ex: Olivier")
            lang = st.selectbox(_('LANG_LABEL'), options=["es", "en"], format_func=lambda x: "🇪🇸 Español" if x == "es" else "🇺🇸 English")
            
            # Guardar idioma en tiempo real para que la UI se actualice
            if lang != st.session_state.get('language'):
                st.session_state.language = lang
                st.rerun()

        with tab2:
            st.markdown("### Paso 2: Perfil de Riesgo")
            st.info("Esto configurará tus parámetros iniciales de Stop Loss y Gestión de Capital.")
            risk = st.radio(
                _('RISK_PROFILE_LABEL'),
                options=["conservative", "moderate", "aggressive"],
                format_func=lambda x: _(f'RISK_{x.upper()}')
            )

        with tab3:
            st.markdown(f"### Paso 3: { _('NAV_HISTORY') }")
            
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"**📈 { _('TUT_STEP1_TITLE') }**")
                st.caption(_('TUT_STEP1_DESC'))
            with c2:
                st.markdown(f"**🌍 { _('TUT_STEP2_TITLE') }**")
                st.caption(_('TUT_STEP2_DESC'))
            
            st.markdown("---")
            if st.button(_('START_BUTTON'), type="primary", width="stretch"):
                if name:
                    # Persistir en DB
                    db.set_system_status('user_name', name)
                    db.set_system_status('language', lang)
                    db.set_system_status('risk_profile', risk)
                    db.set_system_status('onboarding_completed', 'True')
                    
                    # Actualizar sesión y relanzar
                    st.session_state.onboarding_completed = True
                    st.session_state.user_name = name
                    st.success("¡Sistema inicializado con éxito!")
                    time.sleep(1.5)
                    st.rerun()
                else:
                    st.error("Por favor, introduce tu nombre para continuar.")

def is_onboarding_done():
    """Verifica si el usuario ya completó el onboarding"""
    if "onboarding_completed" in st.session_state:
        return st.session_state.onboarding_completed
    
    db = st.session_state.get('db')
    if db:
        status = db.get_system_status('onboarding_completed')
        done = str(status).lower() == 'true'
        st.session_state.onboarding_completed = done
        if done:
            st.session_state.user_name = db.get_system_status('user_name', 'User')
            st.session_state.language = db.get_system_status('language', 'es')
        return done
    return False
