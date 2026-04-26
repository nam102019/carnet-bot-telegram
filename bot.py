#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 Bot Vitrine - Carnet de Sauvegarde
Hébergé sur Railway.app
"""

import logging
import sqlite3
import os
import csv
import io
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    ContextTypes, ConversationHandler, MessageHandler, filters
)
from telegram.request import HTTPXRequest

# Configuration Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 🔑 Token depuis les variables d'environnement
TOKEN = os.getenv("TELEGRAM_TOKEN", "8717485898:AAHXQqG-M1v1MqKRHTWyQ_nOiP8oJeY15xE")

# 📂 Base de données (dans le dossier actuel sur Railway)
DB_NAME = "carnet_vitrine.db"

# 📋 Structure Catégories
CATEGORIES = {
    "1xbet": {"emoji": "🔵", "subs": ["Partenaire promo code", "Agent Mobcash"]},
    "Afropari": {"emoji": "🟣", "subs": ["Partenaire promo code", "Agent Mobcash"]},
    "Melbet": {"emoji": "🟡", "subs": ["Partenaire promo code", "Agent Mobcash"]}
}

# États conversation
STATE_PRENOM, STATE_NOM, STATE_CONTENT, STATE_EDIT = range(4)
user_sessions = {}

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
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
    conn.close()
    logger.info(f"✅ DB initialisée: {DB_NAME}")

# ==================== COMMANDES ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 *Bienvenue !*\n\n🏪 Utilisez le menu ci-dessous.", parse_mode="Markdown")
    await show_vitrine_menu(update)

async def show_vitrine_menu(update: Update):
    keyboard = []
    for cat_name, cat_info in CATEGORIES.items():
        keyboard.append([InlineKeyboardButton(f"{cat_info['emoji']} {cat_name}", callback_data=f"cat_{cat_name}")])
    
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.edit_message_text(
            "🏪 *CATÉGORIES*\n\nChoisissez :",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "🏪 *CATÉGORIES*\n\nChoisissez :",
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
        f"📂 *{cat.upper()}*\n\nSections :",
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
        [InlineKeyboardButton("➕ Ajouter", callback_data=f"add_{cat}_{parts[2]}")],
        [InlineKeyboardButton("📋 Voir", callback_data=f"list_{cat}_{parts[2]}")],
        [InlineKeyboardButton("🔙 Retour", callback_data=f"cat_{cat}")]
    ]
    
    await query.edit_message_text(
        f"📂 {cat}\n📄 {sub}\n\nAction :",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def start_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_", 2)
    cat = parts[1]
    sub = parts[2].replace("_", " ")
    
    user_sessions[query.from_user.id] = {"cat": cat, "sub": sub, "step": "prenom"}
    
    await query.edit_message_text(
        f"➕ *Nouvelle Fiche*\n\n*1/3 Prénom :*",
        parse_mode="Markdown"
    )
    return STATE_PRENOM

async def get_prenom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prenom = update.message.text.strip()
    uid = update.effective_user.id
    user_sessions[uid]["prenom"] = prenom
    user_sessions[uid]["step"] = "nom"
    
    await update.message.reply_text(f"✅ {prenom}\n\n*2/3 Nom :*", parse_mode="Markdown")
    return STATE_NOM

async def get_nom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nom = update.message.text.strip()
    uid = update.effective_user.id
    user_sessions[uid]["nom"] = nom
    user_sessions[uid]["step"] = "content"
    
    await update.message.reply_text(f"✅ {nom}\n\n*3/3 Contenu :*", parse_mode="Markdown")
    return STATE_CONTENT

async def save_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    content = update.message.text
    uid = update.effective_user.id
    sess = user_sessions.get(uid)
    
    if not sess:
        return ConversationHandler.END
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO notes (category, subcategory, prenom, nom, content) VALUES (?,?,?,?,?)",
              (sess["cat"], sess["sub"], sess["prenom"], sess["nom"], content))
    conn.commit()
    nid = c.lastrowid
    conn.close()
    
    del user_sessions[uid]
    
    await update.message.reply_text(f"✅ *Enregistré !*\nID: `{nid}`", parse_mode="Markdown")
    await show_vitrine_menu(update)
    return ConversationHandler.END

async def show_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_", 2)
    cat = parts[1]
    sub = parts[2].replace("_", " ")
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, prenom, nom, content FROM notes WHERE category=? AND subcategory=? ORDER BY nom, prenom", (cat, sub))
    notes = c.fetchall()
    conn.close()
    
    if not notes:
        await query.edit_message_text("📭 Aucune fiche.")
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
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM notes WHERE id=?", (nid,))
    note = c.fetchone()
    conn.close()
    
    if not note:
        await query.edit_message_text("❌ Introuvable")
        return
    
    text = (f"🆔 ID: `{note[0]}`\n📂 {note[1]} → {note[2]}\n"
            f"👤 *{note[3]} {note[4]}*\n📝 `{note[5]}`\n🕒 {note[6]}")
    
    keyboard = [
        [InlineKeyboardButton("✏️ Modifier", callback_data=f"edit_{nid}")],
        [InlineKeyboardButton("🗑️ Supprimer", callback_data=f"del_{nid}")],
        [InlineKeyboardButton("🔙 Retour", callback_data=f"list_{note[1]}_{note[2].replace(' ', '_')}")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def start_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    nid = int(query.data.split("_")[1])
    user_sessions[query.from_user.id] = {"edit_id": nid, "step": "edit"}
    
    await query.edit_message_text("✏️ *Nouveau contenu :*", parse_mode="Markdown")
    return STATE_EDIT

async def save_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_content = update.message.text
    uid = update.effective_user.id
    sess = user_sessions.get(uid)
    
    if not sess or "edit_id" not in sess:
        return ConversationHandler.END
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE notes SET content=? WHERE id=?", (new_content, sess["edit_id"]))
    conn.commit()
    conn.close()
    
    del user_sessions[uid]
    await update.message.reply_text("✅ *Modifié !*", parse_mode="Markdown")
    await show_vitrine_menu(update)
    return ConversationHandler.END

async def confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    nid = int(query.data.split("_")[1])
    
    keyboard = [
        [InlineKeyboardButton("✅ Oui", callback_data=f"exec_del_{nid}")],
        [InlineKeyboardButton("❌ Non", callback_data=f"view_{nid}")]
    ]
    
    await query.edit_message_text("⚠️ *Confirmer suppression ?*", 
                                  reply_markup=InlineKeyboardMarkup(keyboard), 
                                  parse_mode="Markdown")

async def exec_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    nid = int(query.data.split("_")[2])
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM notes WHERE id=?", (nid,))
    conn.commit()
    conn.close()
    
    await query.edit_message_text("🗑️ *Supprimé.*", parse_mode="Markdown")

# ==================== POINT D'ENTRÉE ====================
def main():
    init_db()
    logger.info("🚀 Démarrage Bot Vitrine sur Railway...")
    
    # Configuration connexion optimisée
    request = HTTPXRequest(
        read_timeout=60,
        write_timeout=60,
        connect_timeout=30,
        pool_timeout=30
    )
    
    app = (Application.builder()
           .token(TOKEN)
           .request(request)
           .get_updates_request(request)
           .build())
    
    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(show_vitrine_menu, pattern="^main$"))
    app.add_handler(CallbackQueryHandler(category_view, pattern="^cat_"))
    app.add_handler(CallbackQueryHandler(subcategory_view, pattern="^sub_"))
    app.add_handler(CallbackQueryHandler(show_list, pattern="^list_"))
    app.add_handler(CallbackQueryHandler(view_detail, pattern="^view_"))
    app.add_handler(CallbackQueryHandler(confirm_delete, pattern="^del_"))
    app.add_handler(CallbackQueryHandler(exec_delete, pattern="^exec_del_"))
    
    # Conversations
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(start_add, pattern="^add_")],
        states={
            STATE_PRENOM: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_prenom)],
            STATE_NOM: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_nom)],
            STATE_CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_note)],
        },
        fallbacks=[]
    ))
    
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(start_edit, pattern="^edit_")],
        states={STATE_EDIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_edit)]},
        fallbacks=[]
    ))
    
    logger.info("✅ Bot prêt !")
    print("🤖 Bot démarré sur Railway.app")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
