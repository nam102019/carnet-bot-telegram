#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 Bot Vitrine - Carnet de Sauvegarde
✅ Boutons corrigés + Confirmations explicites + PostgreSQL/SQLite
"""

import logging
import os
import csv
import io
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    ContextTypes, ConversationHandler, MessageHandler, filters
)
from telegram.request import HTTPXRequest

# Import PostgreSQL
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

# 📱 Menu permanent en bas
QUICK_MENU = ReplyKeyboardMarkup([
    ["🔵 1xbet", "🟣 Afropari", "🟡 Melbet"],
    ["➕ Ajouter", "📋 Voir fiches", "📤 Exporter"],
    ["🏠 Accueil", "❓ Aide"]
], resize_keyboard=True, is_persistent=True)

# 🎯 Filtres STRICTS pour éviter les conflits
MENU_TEXT_REGEX = r'^(🔵 1xbet|🟣 Afropari|🟡 Melbet|➕ Ajouter| Voir fiches|📤 Exporter|🏠 Accueil|❓ Aide)$'
MENU_FILTER = filters.Regex(MENU_TEXT_REGEX)
INPUT_FILTER = filters.TEXT & ~filters.COMMAND & ~MENU_FILTER  # Capture TOUT sauf les commandes et les boutons

# États de conversation
STATE_PRENOM, STATE_NOM, STATE_CONTENT, STATE_EDIT = range(4)
user_sessions = {}

def get_db_connection():
    if USE_POSTGRES:
        return psycopg2.connect(DATABASE_URL)
    return sqlite3.connect("carnet_vitrine.db")

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    if USE_POSTGRES:
        cur.execute('''CREATE TABLE IF NOT EXISTS notes (
            id SERIAL PRIMARY KEY, category TEXT NOT NULL, subcategory TEXT NOT NULL,
            prenom TEXT NOT NULL, nom TEXT NOT NULL, content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    else:
        cur.execute('''CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT NOT NULL, subcategory TEXT NOT NULL,
            prenom TEXT NOT NULL, nom TEXT NOT NULL, content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    cur.close()
    conn.close()
    logger.info(f"✅ DB initialisée : {'PostgreSQL ✅' if USE_POSTGRES else 'SQLite'}")

# ==================== 🏠 ACCUEIL & MENU RAPIDE ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Bienvenue !*\n\n🏪 Utilisez le menu en bas pour naviguer rapidement.",
        reply_markup=QUICK_MENU,
        parse_mode="Markdown"
    )

async def handle_quick_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère EXCLUSIVEMENT les clics sur le menu permanent"""
    text = update.message.text.strip()
    cat_map = {"🔵 1xbet": "1xbet", "🟣 Afropari": "Afropari", "🟡 Melbet": "Melbet"}
    
    # Annuler toute conversation en cours si l'utilisateur clique sur le menu
    if context.user_data.get('conv_active'):
        context.user_data.clear()

    if text in cat_map:
        cat = cat_map[text]
        kb = [[InlineKeyboardButton(f"📄 {sub}", callback_data=f"sub_{cat}_{sub.replace(' ', '_')}")] for sub in CATEGORIES[cat]["subs"]]
        kb.append([InlineKeyboardButton("🔙 Retour", callback_data="main")])
        await update.message.reply_text(f"📂 *{cat.upper()}*\n\nSélectionnez une section :", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        
    elif text == "➕ Ajouter":
        kb = [[InlineKeyboardButton(f"{CATEGORIES[c]['emoji']} {c}", callback_data=f"add_{c}_{CATEGORIES[c]['subs'][0].replace(' ', '_')}")] for c in CATEGORIES]
        await update.message.reply_text("➕ *Ajouter une fiche*\n\nChoisissez une catégorie :", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        
    elif text == "📋 Voir fiches":
        kb = [[InlineKeyboardButton(f"{CATEGORIES[c]['emoji']} {c}", callback_data=f"list_{c}_{CATEGORIES[c]['subs'][0].replace(' ', '_')}")] for c in CATEGORIES]
        await update.message.reply_text("📋 *Voir les fiches*\n\nChoisissez une catégorie :", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        
    elif text == "📤 Exporter":
        kb = [[InlineKeyboardButton(f"{CATEGORIES[c]['emoji']} {c}", callback_data=f"export_{c}_{CATEGORIES[c]['subs'][0].replace(' ', '_')}")] for c in CATEGORIES]
        await update.message.reply_text("📤 *Exporter CSV*\n\nChoisissez une catégorie :", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        
    elif text == "🏠 Accueil":
        kb = [[InlineKeyboardButton(f"{CATEGORIES[c]['emoji']} {c}", callback_data=f"cat_{c}")] for c in CATEGORIES]
        await update.message.reply_text("🏪 *CATÉGORIES*\n\nChoisissez une marque :", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        
    elif text == "❓ Aide":
        await update.message.reply_text(
            "❓ *Aide Rapide*\n\n"
            "• Le menu en bas reste affiché en permanence.\n"
            "• Cliquez sur une catégorie pour voir ses sous-sections.\n"
            "• Les fiches sont classées par nom/prénom.\n"
            "• Chaque action affiche un message de confirmation.",
            parse_mode="Markdown"
        )

# ==================== NAVIGATION INLINE ====================
async def show_vitrine_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    kb = [[InlineKeyboardButton(f"{CATEGORIES[c]['emoji']} {c}", callback_data=f"cat_{c}")] for c in CATEGORIES]
    await query.edit_message_text("🏪 *CATÉGORIES*\n\nChoisissez une marque :", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def category_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cat = query.data.replace("cat_", "")
    kb = [[InlineKeyboardButton(f"📄 {sub}", callback_data=f"sub_{cat}_{sub.replace(' ', '_')}")] for sub in CATEGORIES[cat]["subs"]]
    kb.append([InlineKeyboardButton("🔙 Retour", callback_data="main")])
    await query.edit_message_text(f"📂 *{cat.upper()}*\n\nSélectionnez une section :", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def subcategory_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_", 2)
    cat, sub = parts[1], parts[2].replace("_", " ")
    kb = [
        [InlineKeyboardButton("➕ Ajouter", callback_data=f"add_{cat}_{parts[2]}")],
        [InlineKeyboardButton("📋 Voir", callback_data=f"list_{cat}_{parts[2]}")],
        [InlineKeyboardButton("🔙 Retour", callback_data=f"cat_{cat}")]
    ]
    await query.edit_message_text(f"📂 {cat}\n📄 {sub}\n\nAction :", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

# ==================== ➕ AJOUT AVEC CONFIRMATION ====================
async def start_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['conv_active'] = True
    parts = query.data.split("_", 2)
    user_sessions[query.from_user.id] = {"cat": parts[1], "sub": parts[2].replace("_", " "), "step": "prenom"}
    await query.edit_message_text(f"➕ *NOUVELLE FICHE*\n\n*1/3 Entrez le Prénom :*", parse_mode="Markdown")
    return STATE_PRENOM

async def get_prenom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_sessions[uid]["prenom"] = update.message.text.strip()
    await update.message.reply_text(f"✅ Prénom enregistré.\n\n*2/3 Entrez le Nom :*", parse_mode="Markdown")
    return STATE_NOM

async def get_nom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_sessions[uid]["nom"] = update.message.text.strip()
    await update.message.reply_text(f"✅ Nom enregistré.\n\n*3/3 Entrez le contenu :*", parse_mode="Markdown")
    return STATE_CONTENT

async def save_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    sess = user_sessions.get(uid)
    if not sess: return ConversationHandler.END
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO notes (category, subcategory, prenom, nom, content) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (sess["cat"], sess["sub"], sess["prenom"], sess["nom"], update.message.text))
    conn.commit()
    nid = cur.fetchone()[0]
    cur.close(); conn.close()
    del user_sessions[uid]
    context.user_data.pop('conv_active', None)
    
    await update.message.reply_text(
        f"✅ *FICHE AJOUTÉE AVEC SUCCÈS !*\n\n"
        f"🆔 ID : `{nid}`\n"
        f"👤 {sess['prenom']} {sess['nom']}\n"
        f"📂 {sess['cat']} → {sess['sub']}\n"
        f"💾 *Données sauvegardées en base.*",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

# ==================== 📋 LISTE & DÉTAIL ====================
async def show_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_", 2)
    cat, sub = parts[1], parts[2].replace("_", " ")
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, prenom, nom, content FROM notes WHERE category=%s AND subcategory=%s ORDER BY nom, prenom", (cat, sub))
    notes = cur.fetchall()
    cur.close(); conn.close()
    
    if not notes:
        await query.edit_message_text(f"📭 *Aucune fiche trouvée*\n📂 {cat} → {sub}", parse_mode="Markdown")
        return
    
    text, kb = f"📋 *LISTE DES FICHES*\n📂 {cat} → {sub}\n─────────────\n\n", []
    for nid, p, n, c in notes:
        text += f"🔹 *{p} {n}*\n   `{c[:30]}...`\n\n"
        kb.append([InlineKeyboardButton(f"👤 {p} {n}", callback_data=f"view_{nid}")])
    kb.append([InlineKeyboardButton("🔙 Retour", callback_data=f"sub_{cat}_{sub.replace(' ', '_')}")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def view_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    nid = int(query.data.split("_")[1])
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM notes WHERE id=%s", (nid,))
    note = cur.fetchone()
    cur.close(); conn.close()
    if not note: return await query.edit_message_text("❌ Fiche introuvable.", parse_mode="Markdown")
    
    text = f"🆔 ID: `{note[0]}`\n📂 {note[1]} → {note[2]}\n👤 *{note[3]} {note[4]}*\n📝 *Contenu :*\n`{note[5]}`\n🕒 {note[6]}"
    kb = [
        [InlineKeyboardButton("✏️ Modifier", callback_data=f"edit_{nid}")],
        [InlineKeyboardButton("🗑️ Supprimer", callback_data=f"del_{nid}")],
        [InlineKeyboardButton("🔙 Retour", callback_data=f"list_{note[1]}_{note[2].replace(' ', '_')}")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

# ==================== ✏️ MODIFICATION AVEC CONFIRMATION ====================
async def start_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['conv_active'] = True
    nid = int(query.data.split("_")[1])
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT content, category, subcategory FROM notes WHERE id=%s", (nid,))
    res = cur.fetchone()
    cur.close(); conn.close()
    if not res: return await query.edit_message_text("❌ Fiche introuvable.", parse_mode="Markdown")
    
    content, cat, sub = res
    context.user_data.update({'edit_id': nid, 'cat': cat, 'sub': sub})
    
    preview = content if len(content) < 300 else content[:300] + "..."
    await query.edit_message_text(
        f"✏️ *MODIFICATION DE FICHE*\n"
        f"📂 {cat} → {sub}\n\n"
        f"📝 *Texte actuel :*\n`{preview}`\n\n"
        f"👇 *Envoyez directement le NOUVEAU texte :*",
        parse_mode="Markdown"
    )
    return STATE_EDIT

async def save_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nid = context.user_data.get('edit_id')
    cat, sub = context.user_data.get('cat'), context.user_data.get('sub')
    if not nid: return ConversationHandler.END
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE notes SET content=%s WHERE id=%s", (update.message.text, nid))
    conn.commit()
    cur.close(); conn.close()
    
    context.user_data.pop('conv_active', None)
    context.user_data.clear()
    
    await update.message.reply_text(
        f"✅ *FICHE MODIFIÉE AVEC SUCCÈS !*\n\n"
        f"🆔 ID : `{nid}`\n"
        f"📂 {cat} → {sub}\n"
        f"📝 Contenu mis à jour.\n"
        f"💾 *Changements sauvegardés en base.*",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

# ==================== 🗑️ SUPPRESSION AVEC CONFIRMATION ====================
async def confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    nid = int(query.data.split("_")[1])
    kb = [[InlineKeyboardButton("✅ Oui, supprimer", callback_data=f"exec_del_{nid}")], [InlineKeyboardButton("❌ Annuler", callback_data=f"view_{nid}")]]
    await query.edit_message_text(
        "⚠️ *CONFIRMATION DE SUPPRESSION*\n\n"
        "Voulez-vous vraiment supprimer cette fiche ?\n"
        "⚠️ *Cette action est irréversible.*",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
    )

async def exec_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    nid = int(query.data.split("_")[2])
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM notes WHERE id=%s", (nid,))
    conn.commit()
    cur.close(); conn.close()
    
    await query.edit_message_text(
        f"🗑️ *FICHE SUPPRIMÉE AVEC SUCCÈS !*\n\n"
        f"🆔 ID : `{nid}`\n"
        f"⚠️ *Action irréversible.*\n"
        f"💾 *Base de données mise à jour.*",
        parse_mode="Markdown"
    )

# ==================== 📤 EXPORT ====================
async def export_csv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_", 2)
    cat, sub = parts[1], parts[2].replace("_", " ")
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT prenom, nom, subcategory, content, created_at FROM notes WHERE category=%s AND subcategory=%s ORDER BY nom, prenom", (cat, sub))
    notes = cur.fetchall()
    cur.close(); conn.close()
    
    if not notes:
        await query.edit_message_text("📭 Aucune donnée à exporter.")
        return
    
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(['Prénom', 'Nom', 'Sous-catégorie', 'Contenu', 'Date'])
    for row in notes: writer.writerow(row)
    
    file_io = io.BytesIO(output.getvalue().encode('utf-8-sig'))
    file_io.name = f"Export_{cat}_{sub.replace(' ', '_')}.csv"
    
    await query.message.reply_document(document=file_io, caption=f"📊 *EXPORT CSV*\n{cat} - {sub}\n{len(notes)} fiche(s)", parse_mode="Markdown")
    await query.edit_message_text("✅ *Export envoyé ! Fichier CSV joint ci-dessus.*", parse_mode="Markdown")

# ==================== 🚀 POINT D'ENTRÉE ====================
def main():
    init_db()
    logger.info("🚀 Démarrage Bot Vitrine...")
    
    app = Application.builder().token(TOKEN).build()
    
    # 1️⃣ Menu rapide (filtre STRICT)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(MENU_FILTER, handle_quick_menu))
    
    # 2️⃣ Callbacks Inline
    app.add_handler(CallbackQueryHandler(show_vitrine_menu, pattern="^main$"))
    app.add_handler(CallbackQueryHandler(category_view, pattern="^cat_"))
    app.add_handler(CallbackQueryHandler(subcategory_view, pattern="^sub_"))
    app.add_handler(CallbackQueryHandler(show_list, pattern="^list_"))
    app.add_handler(CallbackQueryHandler(view_detail, pattern="^view_"))
    app.add_handler(CallbackQueryHandler(confirm_delete, pattern="^del_"))
    app.add_handler(CallbackQueryHandler(exec_delete, pattern="^exec_del_"))
    app.add_handler(CallbackQueryHandler(export_csv, pattern="^export_"))
    
    # 3️⃣ Conversations (filtre INPUT_FILTER pour ignorer les clics menu)
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(start_add, pattern="^add_")],
        states={
            STATE_PRENOM: [MessageHandler(INPUT_FILTER, get_prenom)],
            STATE_NOM: [MessageHandler(INPUT_FILTER, get_nom)],
            STATE_CONTENT: [MessageHandler(INPUT_FILTER, save_note)],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
        name="add_conv"
    ))
    
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(start_edit, pattern="^edit_")],
        states={STATE_EDIT: [MessageHandler(INPUT_FILTER, save_edit)]},
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
        name="edit_conv"
    ))
    
    logger.info("✅ Bot prêt !")
    print("🤖 Bot démarré. Boutons corrigés & confirmations actives.")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
