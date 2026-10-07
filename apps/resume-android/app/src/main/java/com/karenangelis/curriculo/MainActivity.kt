package com.karenangelis.curriculo

import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import android.widget.*
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

class MainActivity : Activity() {
    private val ink = Color.rgb(16,18,17)
    private val panel = Color.rgb(28,33,27)
    private val white = Color.rgb(241,240,233)
    private val muted = Color.rgb(166,170,162)
    private val lime = Color.rgb(197,241,106)
    private val executor = Executors.newSingleThreadExecutor()
    private lateinit var profile: JSONObject
    private lateinit var content: LinearLayout
    private lateinit var status: TextView
    private lateinit var refresh: Button
    private val tabs = linkedMapOf<String, Button>()
    private var selected = "Habilidades"
    private var query = ""
    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()
    private fun rows(data: JSONArray) = (0 until data.length()).map { data.getJSONObject(it) }
    private fun text(value: String, size: Float = 15f, color: Int = white, bold: Boolean = false): TextView = TextView(this).apply {
        text = value; textSize = size; setTextColor(color); setPadding(0,dp(5),0,dp(6))
        if(bold) setTypeface(typeface, Typeface.BOLD)
    }
    private fun box(color: Int = panel): GradientDrawable = GradientDrawable().apply {
        setColor(color); cornerRadius = dp(14).toFloat()
    }
    private fun column() = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
    private fun card(parent: LinearLayout): LinearLayout = column().apply {
        background = box(); setPadding(dp(18),dp(15),dp(18),dp(15))
        parent.addView(this,LinearLayout.LayoutParams(-1,-2).apply { bottomMargin = dp(14) })
    }
    private fun button(label: String, action: () -> Unit): Button = Button(this).apply {
        text = label; isAllCaps = false; textSize = 13f; setTextColor(ink); background = box(lime)
        minHeight = dp(44); setPadding(dp(16),dp(8),dp(16),dp(8)); setOnClickListener { action() }
    }
    private fun open(url: String) {
        val target = Uri.parse(url)
        if(target.scheme != "https") return
        try { startActivity(Intent(Intent.ACTION_VIEW,target)) }
        catch (_: Exception) { Toast.makeText(this,"Nenhum aplicativo disponível para abrir esse link.",Toast.LENGTH_SHORT).show() }
    }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_STATE_ALWAYS_HIDDEN)
        selected = savedInstanceState?.getString("section") ?: "Habilidades"
        query = savedInstanceState?.getString("query") ?: ""
        profile = try { JSONObject(filesDir.resolve("profile.json").readText()) }
        catch (_: Exception) { JSONObject(assets.open("profile.json").bufferedReader().use { it.readText() }) }
        val root = column().apply { setBackgroundColor(ink); setPadding(dp(20),dp(12),dp(20),dp(10)) }
        setContentView(root)
        root.isFocusableInTouchMode=true
        root.requestFocus()
        root.setOnApplyWindowInsetsListener { view,insets ->
            view.setPadding(dp(20)+insets.systemWindowInsetLeft,dp(12)+insets.systemWindowInsetTop,dp(20)+insets.systemWindowInsetRight,dp(10)+insets.systemWindowInsetBottom);insets
        }
        root.addView(text("ka · Karen Angelis",27f,lime,true))
        root.addView(text("Currículo Android · Kotlin + API Go",12f,muted))
        val navigation = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        val navScroll = HorizontalScrollView(this).apply { isHorizontalScrollBarEnabled = false; addView(navigation) }
        root.addView(navScroll)
        for(label in listOf("Habilidades","Experiência","Formação","Idiomas","Projetos","Contato")) {
            val item = button(label) { selected = label; render() }
            navigation.addView(item,LinearLayout.LayoutParams(-2,dp(42)).apply { rightMargin = dp(8); topMargin = dp(10); bottomMargin = dp(10) })
            tabs[label] = item
        }
        content = column()
        val scroll = ScrollView(this).apply { isFillViewport = true; addView(content) }
        root.addView(scroll,LinearLayout.LayoutParams(-1,0,1f))
        status = text("Dados incluídos no app · disponível offline",11f,muted)
        root.addView(status)
        refresh = button("Atualizar pela API Go") { fetchProfile() }
        root.addView(refresh)
        render()
        fetchProfile()
    }
    private fun render() {
        content.removeAllViews()
        for((label,tab) in tabs){tab.background=box(if(label==selected) lime else panel);tab.setTextColor(if(label==selected) ink else white);tab.isSelected=label==selected}
        when(selected) {
            "Habilidades" -> {
                content.addView(text(profile.optString("fullName", "Karen Angelis"),23f,white,true))
                content.addView(text(profile.optString("summary"),14f,muted))
                val search = EditText(this).apply {
                    hint = "Buscar habilidade: Python, Flutter, UX…"; setHintTextColor(muted);setTextColor(white)
                    isSingleLine=true;setText(query);setPadding(dp(12),dp(12),dp(12),dp(12));background=box()
                    contentDescription="Buscar habilidade"
                }
                content.addView(search)
                val groups = column(); content.addView(groups)
                fun filter() {
                    groups.removeAllViews()
                    val term = query.trim().lowercase()
                    for(group in rows(profile.getJSONArray("skillGroups"))) {
                        val items = group.getJSONArray("items")
                        val labels = (0 until items.length()).map { items.getString(it) }
                        val title = group.getString("title")
                        if(term.isNotEmpty() && !(title+" "+labels.joinToString(" ")+" "+group.getString("example")).lowercase().contains(term)) continue
                        val area = card(groups)
                        val detail = column().apply { visibility=if(term.isEmpty()) View.GONE else View.VISIBLE }
                        val toggle = button(title+" · "+labels.size) { detail.visibility=if(detail.visibility==View.GONE) View.VISIBLE else View.GONE }
                        area.addView(toggle)
                        detail.addView(text(group.getString("description"),14f,muted))
                        detail.addView(text(labels.joinToString("  ·  "),15f))
                        detail.addView(text(group.getString("example"),13f,muted))
                        area.addView(detail)
                    }
                    if(groups.childCount==0) groups.addView(text("Nenhuma habilidade encontrada. Tente outro termo.",14f,muted))
                }
                search.addTextChangedListener(object : TextWatcher {
                    override fun beforeTextChanged(s: CharSequence?,start: Int,count: Int,after: Int) {}
                    override fun onTextChanged(s: CharSequence?,start: Int,before: Int,count: Int) { query=s.toString();filter() }
                    override fun afterTextChanged(s: Editable?) {}
                });filter()
                content.addView(text("Como eu trabalho",22f,lime,true))
                for(item in rows(profile.getJSONArray("softSkills"))){val c=card(content);c.addView(text(item.getString("title"),17f,white,true));c.addView(text(item.getString("example"),14f,muted))}
            }
            "Experiência" -> for(item in rows(profile.getJSONArray("experience"))) {
                val c=card(content);c.addView(text(item.getString("period"),12f,lime));c.addView(text(item.getString("company"),20f,white,true));c.addView(text(item.getString("role"),15f));c.addView(text(item.getString("description"),14f,muted))
            }
            "Formação" -> {
                for(item in rows(profile.getJSONArray("education"))){val c=card(content);c.addView(text(item.getString("title"),19f,white,true));c.addView(text(item.getString("institution")+" · "+item.getString("status"),14f,lime));c.addView(text(item.getString("detail"),14f,muted))}
                content.addView(text("Cursos e certificados",22f,lime,true))
                for(item in rows(profile.getJSONArray("courses"))){val c=card(content);c.addView(text(item.getString("title"),17f,white,true));c.addView(text(item.getString("institution")+" · "+item.getString("detail"),14f,muted))}
                content.addView(text("Outros estudos registrados",20f,lime,true))
                val extra=profile.getJSONArray("additionalStudies");for(i in 0 until extra.length())content.addView(text(extra.getString(i),14f,muted))
            }
            "Idiomas" -> for(item in rows(profile.getJSONArray("languages"))){val c=card(content);c.addView(text(item.getString("name"),20f,white,true));c.addView(text(item.getString("level"),15f,muted))}
            "Projetos" -> for(item in rows(profile.getJSONArray("projects"))){val c=card(content);c.addView(text(item.getString("name"),20f,white,true));c.addView(text(item.getString("description"),14f,muted));c.addView(button(item.getString("linkLabel")) { open(item.getString("url")) })}
            "Contato" -> {
                content.addView(text("Vamos conversar?",27f,lime,true))
                content.addView(text("Karen Denich de Angelis",20f,white,true))
                for((label,url) in listOf("WhatsApp · +55 (47) 99733-6808" to profile.getString("whatsapp"),"LinkedIn" to profile.getString("linkedin"),"GitHub" to profile.getString("github"),"Portfólio" to "https://karenangelis.com")) {
                    val c=card(content);c.addView(button(label){open(url)})
                }
            }
        }
    }
    private fun fetchProfile() {
        refresh.isEnabled=false;status.text="Consultando currículo na API Go…"
        executor.execute {
            var connection: HttpURLConnection?=null
            try {
                connection=URL("https://karenangelis.com/api/profile").openConnection() as HttpURLConnection
                connection.connectTimeout=8000;connection.readTimeout=8000
                check(connection.responseCode==200)
                val body=connection.inputStream.bufferedReader().use { it.readText() }
                check(body.length<1_000_000)
                val updated=JSONObject(body);updated.getJSONArray("skillGroups");updated.getJSONArray("education")
                filesDir.resolve("profile.json").writeText(body)
                runOnUiThread { if(!isFinishing&&!isDestroyed){profile=updated;status.text="Currículo atualizado pela API Go";refresh.isEnabled=true;render()} }
            } catch (_: Exception) {
                runOnUiThread { if(!isFinishing&&!isDestroyed){status.text="Sem conexão · currículo disponível offline";refresh.isEnabled=true} }
            } finally { connection?.disconnect() }
        }
    }
    override fun onSaveInstanceState(outState: Bundle) { outState.putString("section",selected);outState.putString("query",query);super.onSaveInstanceState(outState) }
    override fun onDestroy() { executor.shutdownNow();super.onDestroy() }
}
