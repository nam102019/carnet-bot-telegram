#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 Bot Vitrine - Carnet de Sauvegarde
Hébergé sur Railway.app avec PostgreSQL (fallback SQLite)
Fonctionnalités : Vitrine, Prénom/Nom, Modification directe, Export CSV
"""

import logging
import os
import csv
import io
import sqlite3  # ✅ Import global pour éviter NameError
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    ContextTypes, ConversationHandler, MessageHandler, filters
)
from telegram.request import HTTPXRequest

# Import PostgreSQL (Railway l'installera via requirements.txt)
try:
    import psycopg2
except ImportError:
    pass

# Configuration Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 🔑 Token
TOKEN = os.getenv("TELEGRAM_TOKEN")

# 🗄️ Base de données
DATABASE_URL = os.getenv("DATABASE_URL")
USE_POSTGRES = DATABASE_URL is not None

# 📋 Catégories
CATEGORIES = {
    "1xbet": {"emoji": "🔵", "subs": ["Partenaire promo code", "Agent Mobcash"]},
    "Afropari": {"emoji": "🟣", "subs": ["Partenaire promo code", "Agent Mobcash"]},
    "Melbet": {"emoji": "🟡", "subs": ["Partenaire promo code", "Agent Mobcash"]}
}

# États de conversation
STATE_PRENOM, STATE_NOM, STATE_CONTENT, STATE_EDIT = range(4)
user_sessions = {}

def get_db_connection():
    """Retourne une connexion à la BDD (PostgreSQL ou SQLite)"""
    if USE_POSTGRES:
        return psycopg2.connect(DATABASE_URL)
    else:
        return sqlite3.connect("carnet_vitrine.db")

def init_db():
    """Initialise la BDD"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    if USE_POSTGRES:
        cur.execute('''
            CREATE TABLE IF NOT EXISTS notes (
                id SERIAL PRIMARY KEY,
                category TEXT NOT NULL,
                subcategory TEXT NOT NULL,
                prenom TEXT NOT NULL,
                nom TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
    else:
        cur.execute('''
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                subcategory TEXT NOT NULL,
                prenom TEXT NOT NULL,
                nom TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
    
    conn.commit()
    cur.close()
    conn.close()
    db_type = "PostgreSQL ✅" if USE_POSTGRES else "SQLite"
    logger.info(f"✅ DB initialisée : {db_type}")

# ==================== COMMANDES & MENUS ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 *Bienvenue !*\n\n🏪 Utilisez le menu ci-dessous.", parse_mode="Markdown")
    await show_vitrine_menu(update)

async def show_vitrine_menu(update: Update):
    keyboard = []
    for cat_name, cat_info in CATEGORIES.items():
        keyboard.append([InlineKeyboardButton(f"{cat_info['emoji']} {cat_name}", callback_data=f"cat_{cat_name}")])
    
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.edit_message_text(
            "🏪 *CATÉGORIES*\n\nChoisissez une marque :",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "🏪 *CATÉGORIES*\n\nChoisissez une marque :",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

async def category_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cat = query.data.replace("cat_", "")
    
    keyboard = []
    for sub in CATEGORIES[cat]["subs"]:
        safe_sub = sub.replace(" ", "_")
        keyboard.append([InlineKeyboardButton(f"📄 {sub}", callback_data=f"sub_{cat}_{safe_sub}")])
    keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data="main")])
    
    await query.edit_message_text(
        f"📂 *{cat.upper()}*\n\nSélectionnez une section :",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def subcategory_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_", 2)
    cat = parts[1]
    sub = parts[2].replace("_", " ")
    
    keyboard = [
        [InlineKeyboardButton("➕ Ajouter une fiche", callback_data=f"add_{cat}_{parts[2]}")],
        [InlineKeyboardButton("📋 Voir les fiches", callback_data=f"list_{cat}_{parts[2]}")],
        [InlineKeyboardButton("🔙 Retour", callback_data=f"cat_{cat}")]
    ]
    
    await query.edit_message_text(
        f"📂 {cat}\n📄 {sub}\n\nQue souhaitez-vous faire ?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

# ==================== AJOUT DE FICHE ====================
async def start_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_", 2)
    cat = parts[1]
    sub = parts[2].replace("_", " ")
    
    user_sessions[query.from_user.id] = {"cat": cat, "sub": sub, "step": "prenom"}
    
    await query.edit_message_text(
        f"➕ *NOUVELLE FICHE*\n📂 {cat} → {sub}\n\n*1/3 Entrez le Prénom :*",
        parse_mode="Markdown"
    )
    return STATE_PRENOM

async def get_prenom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prenom = update.message.text.strip()
    uid = update.effective_user.id
    user_sessions[uid]["prenom"] = prenom
    user_sessions[uid]["step"] = "nom"
    
    await update.message.reply_text(f"✅ Prénom : *{prenom}*\n\n*2/3 Entrez le Nom :*", parse_mode="Markdown")
    return STATE_NOM

async def get_nom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nom = update.message.text.strip()
    uid = update.effective_user.id
    user_sessions[uid]["nom"] = nom
    user_sessions[uid]["step"] = "content"
    
    await update.message.reply_text(f"✅ Nom : *{nom}*\n\n*3/3 Entrez le contenu de la fiche :*", parse_mode="Markdown")
    return STATE_CONTENT

async def save_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    content = update.message.text
    uid = update.effective_user.id
    sess = user_sessions.get(uid)
    
    if not sess:
        return ConversationHandler.END
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO notes (category, subcategory, prenom, nom, content) VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (sess["cat"], sess["sub"], sess["prenom"], sess["nom"], content)
    )
    conn.commit()
    note_id = cur.fetchone()[0]
    cur.close()
    conn.close()
    
    del user_sessions[uid]
    
    await update.message.reply_text(f"✅ *FICHE ENREGISTRÉE*\n🆔 ID: `{note_id}`", parse_mode="Markdown")
    await show_vitrine_menu(update)
    return ConversationHandler.END

# ==================== LISTE & DÉTAIL ====================
async def show_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_", 2)
    cat = parts[1]
    sub = parts[2].replace("_", " ")
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, prenom, nom, content FROM notes WHERE category=%s AND subcategory=%s ORDER BY nom, prenom",
        (cat, sub)
    )
    notes = cur.fetchall()
    cur.close()
    conn.close()
    
    if not notes:
        await query.edit_message_text(f"📭 *Aucune fiche*\n📂 {cat} → {sub}", parse_mode="Markdown")
        return
    
    text = f"📋 *{cat} → {sub}*\n\n"
    keyboard = []
    for nid, prenom, nom, content in notes:
        text += f"🔹 *{prenom} {nom}*\n   `{content[:30]}...`\n\n"
        keyboard.append([InlineKeyboardButton(f"👤 {prenom} {nom}", callback_data=f"view_{nid}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data=f"sub_{cat}_{sub.replace(' ', '_')}")])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def view_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    nid = int(query.data.split("_")[1])
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM notes WHERE id=%s", (nid,))
    note = cur.fetchone()
    cur.close()
    conn.close()
    
    if not note:
        await query.edit_message_text("❌ Fiche introuvable.", parse_mode="Markdown")
        return
    
    # note: (id, cat, sub, prenom, nom, content, date)
    text = (
        f"🆔 ID: `{note[0]}`\n"
        f"📂 {note[1]} → {note[2]}\n"
        f"👤 *{note[3]} {note[4]}*\n"
        f"📝 *Contenu :*\n`{note[5]}`\n"
        f"🕒 {note[6]}"
    )
    
    keyboard = [
        [InlineKeyboardButton("✏️ Modifier", callback_data=f"edit_{nid}")],
        [InlineKeyboardButton("🗑️ Supprimer", callback_data=f"del_{nid}")],
        [InlineKeyboardButton("🔙 Retour", callback_data=f"list_{note[1]}_{note[2].replace(' ', '_')}")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# ==================== ✏️ MODIFICATION (NOUVEAU COMPORTEMENT) ====================
async def start_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    note_id = int(query.data.split("_")[1])
    
    # Récupérer le contenu actuel
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT content, category, subcategory FROM notes WHERE id=%s", (note_id,))
    result = cur.fetchone()
    cur.close()
    conn.close()
    
    if not result:
        await query.edit_message_text("❌ Fiche introuvable.", parse_mode="Markdown")
        return ConversationHandler.END
    
    current_content, cat, sub = result
    
    # Stocker l'ID pour la sauvegarde
    context.user_data['edit_id'] = note_id
    context.user_data['cat'] = cat
    context.user_data['sub'] = sub
    
    # Afficher le texte actuel et demander le nouveau
    preview = current_content if len(current_content) < 300 else current_content[:300] + "..."
    
    await query.edit_message_text(
        f"✏️ *MODIFICATION*\n"
        f"📂 {cat} → {sub}\n\n"
        f"📝 *Texte actuel :*\n`{preview}`\n\n"
        f"👇 *Envoyez directement le NOUVEAU texte ci-dessous :*",
        parse_mode="Markdown"
    )
    return STATE_EDIT

async def save_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_content = update.message.text
    note_id = context.user_data.get('edit_id')
    cat = context.user_data.get('cat')
    sub = context.user_data.get('sub')
    
    if not note_id:
        await update.message.reply_text("❌ Erreur de session. Recommencez.", parse_mode="Markdown")
        return ConversationHandler.END
    
    # Mise à jour dans la base
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE notes SET content=%s WHERE id=%s", (new_content, note_id))
    conn.commit()
    cur.close()
    conn.close()
    
    await update.message.reply_text(
        f"✅ *FICHE MODIFIÉE*\n"
        f"📂 {cat} → {sub}\n"
        f"📝 Nouveau contenu enregistré.",
        parse_mode="Markdown"
    )
    
    context.user_data.clear()
    await show_vitrine_menu(update)
    return ConversationHandler.END

# ==================== SUPPRESSION ====================
async def confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    nid = int(query.data.split("_")[1])
    
    keyboard = [
        [InlineKeyboardButton("✅ Oui, supprimer", callback_data=f"exec_del_{nid}")],
        [InlineKeyboardButton("❌ Annuler", callback_data=f"view_{nid}")]
    ]
    
    await query.edit_message_text(
        "⚠️ *CONFIRMER SUPPRESSION*\n\nCette action est irréversible.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def exec_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    nid = int(query.data.split("_")[2])
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM notes WHERE id=%s", (nid,))
    conn.commit()
    cur.close()
    conn.close()
    
    await query.edit_message_text("🗑️ *Fiche supprimée avec succès.*", parse_mode="Markdown")

# ==================== POINT D'ENTRÉE ====================
def main():
    init_db()
    logger.info("🚀 Démarrage Bot Vitrine...")
    
    request = HTTPXRequest(read_timeout=60, write_timeout=60, connect_timeout=30)
    
    app = (Application.builder()
           .token(TOKEN)
           .request(request)
           .get_updates_request(request)
           .build())
    
    # Handlers principaux
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(show_vitrine_menu, pattern="^main$"))
    app.add_handler(CallbackQueryHandler(category_view, pattern="^cat_"))
    app.add_handler(CallbackQueryHandler(subcategory_view, pattern="^sub_"))
    app.add_handler(CallbackQueryHandler(show_list, pattern="^list_"))
    app.add_handler(CallbackQueryHandler(view_detail, pattern="^view_"))
    app.add_handler(CallbackQueryHandler(confirm_delete, pattern="^del_"))
    app.add_handler(CallbackQueryHandler(exec_delete, pattern="^exec_del_"))
    
    # Conversation: AJOUT
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(start_add, pattern="^add_")],
        states={
            STATE_PRENOM: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_prenom)],
            STATE_NOM: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_nom)],
            STATE_CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_note)],
        },
        fallbacks=[]
    ))
    
    # Conversation: MODIFICATION
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(start_edit, pattern="^edit_")],
        states={
            STATE_EDIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_edit)],
        },
        fallbacks=[]
    ))
    
    logger.info("✅ Bot prêt !")
    print("🤖 Bot démarré sur Railway.app")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
