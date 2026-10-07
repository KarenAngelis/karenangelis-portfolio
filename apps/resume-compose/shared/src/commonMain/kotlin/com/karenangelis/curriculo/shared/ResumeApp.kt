package com.karenangelis.curriculo.shared

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.horizontalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject

private val Lime=Color(0xffc5f16a)
private val Ink=Color(0xff101211)
private val Panel=Color(0xff1c211b)
private val Muted=Color(0xffa6aaa2)
private val labels=listOf("Habilidades","Experiência","Formação","Idiomas","Projetos","Contato")

@Composable
fun ResumeApp() {
    MaterialTheme(colorScheme=darkColorScheme(primary=Lime,onPrimary=Ink,background=Ink,surface=Panel,onSurface=Color(0xfff1f0e9))) {
        var profile by remember { mutableStateOf(parseProfile(BundledProfile.json)) }
        var selected by rememberSaveable { mutableStateOf(0) }
        var query by rememberSaveable { mutableStateOf("") }
        var status by remember { mutableStateOf("Currículo incluído no app") }
        var busy by remember { mutableStateOf(false) }
        val scope=rememberCoroutineScope()
        val open=LocalUriHandler.current
        fun update() {
            if(busy)return
            busy=true;status="Atualizando currículo…"
            scope.launch {
                try { profile=fetchProfile();status="Currículo atualizado pela API Go" }
                catch(e: CancellationException) { throw e }
                catch(_: Exception) { status="Sem conexão · usando currículo incluído no app" }
                finally { busy=false }
            }
        }
        LaunchedEffect(Unit) { update() }
        fun visit(url: String) {
            val target=if(url.startsWith("/")) "https://karenangelis.com$url" else url
            if(target.startsWith("https://")) open.openUri(target)
        }
        Scaffold(
            containerColor=Ink,
            topBar={ Surface(color=Ink) {
                Row(Modifier.fillMaxWidth().statusBarsPadding().padding(horizontal=18.dp,vertical=12.dp),horizontalArrangement=Arrangement.SpaceBetween) {
                    Column { Text("ka · Karen Angelis",color=Lime,fontSize=21.sp,fontWeight=FontWeight.Bold);Text("Meu currículo",fontSize=11.sp,color=Muted) }
                    TextButton(onClick={update()},enabled=!busy) { Text(if(busy) "Atualizando" else "Atualizar") }
                }
            } },
            bottomBar={ Surface(color=Panel) {
                Column(Modifier.navigationBarsPadding()) {
                    Text(status,fontSize=10.sp,color=Muted,modifier=Modifier.padding(horizontal=18.dp,vertical=4.dp))
                    Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal=8.dp,vertical=4.dp)) {
                        labels.forEachIndexed { index,label ->
                            TextButton(onClick={selected=index},colors=ButtonDefaults.textButtonColors(contentColor=if(selected==index) Lime else Muted)) { Text(label,fontSize=11.sp) }
                        }
                    }
                    TextButton(onClick={visit(profile.text("whatsapp"))},modifier=Modifier.fillMaxWidth()) { Text("Vamos conversar") }
                }
            } }
        ) { padding ->
            key(selected) {
                LazyColumn(Modifier.fillMaxSize().padding(padding),contentPadding=PaddingValues(18.dp),verticalArrangement=Arrangement.spacedBy(14.dp)) {
                    item { Text(labels[selected],fontSize=24.sp,fontWeight=FontWeight.Bold,color=Lime) }
                    when(selected) {
                        0 -> {
                            item { Text(profile.text("fullName"),fontSize=20.sp,fontWeight=FontWeight.Bold);Text(profile.text("role"),fontSize=12.sp,color=Muted) }
                            item { ExpandCard("Sobre mim") { Text(profile.text("summary"),fontSize=13.sp,color=Muted) } }
                            item { OutlinedTextField(value=query,onValueChange={query=it},singleLine=true,label={Text("Buscar habilidade")},placeholder={Text("Python, Flutter, UX…")},modifier=Modifier.fillMaxWidth()) }
                            val term=query.trim().lowercase()
                            val groups=profile.rows("skillGroups").filter { term.isEmpty() || (it.text("title")+" "+it.text("description")+" "+it.text("example")+" "+it.strings("items").joinToString(" ")).lowercase().contains(term) }
                            if(groups.isEmpty()) item { Text("Nenhuma habilidade encontrada. Tente outro termo.",color=Muted) }
                            items(groups,key={it.text("id")}) { group ->
                                key(term) {
                                    ExpandCard(group.text("title")+" · "+group.strings("items").size,term.isNotEmpty()) {
                                        Text(group.text("description"),fontSize=13.sp,color=Muted)
                                        Text(group.strings("items").joinToString("  ·  "),fontSize=14.sp)
                                        Text(group.text("example"),fontSize=12.sp,color=Muted)
                                        TextButton(onClick={visit(group.text("demoUrl"))}) { Text(group.text("demoLabel")) }
                                    }
                                }
                            }
                            item { Text("Como eu trabalho",fontSize=21.sp,color=Lime) }
                            items(profile.rows("softSkills")) { EntryCard(it.text("title"),"",it.text("example")) }
                        }
                        1 -> items(profile.rows("experience")) { EntryCard(it.text("company"),it.text("role")+" · "+it.text("period"),it.text("description")) }
                        2 -> {
                            items(profile.rows("education")) { EntryCard(it.text("title"),it.text("institution")+" · "+it.text("status"),it.text("detail")) }
                            item { Text("Cursos e certificados",fontSize=21.sp,color=Lime) }
                            items(profile.rows("courses")) { EntryCard(it.text("title"),it.text("institution"),it.text("detail")) }
                            item { ExpandCard("Outros estudos registrados") { profile.strings("additionalStudies").forEach { Text(it,fontSize=13.sp,color=Muted) } } }
                        }
                        3 -> items(profile.rows("languages")) { EntryCard(it.text("name"),it.text("level"),"") }
                        4 -> items(profile.rows("projects")) { project ->
                            Card(colors=CardDefaults.cardColors(containerColor=Panel)) { Column(Modifier.padding(18.dp),verticalArrangement=Arrangement.spacedBy(10.dp)) {
                                Text(project.text("name"),fontSize=19.sp,fontWeight=FontWeight.Bold)
                                Text(project.text("description"),fontSize=13.sp,color=Muted)
                                TextButton(onClick={visit(project.text("url"))}) { Text(project.text("linkLabel")) }
                            } }
                        }
                        5 -> {
                            item { Text("Karen Denich de Angelis",fontSize=21.sp);Text("Vamos construir algo?",color=Muted) }
                            items(listOf("WhatsApp" to profile.text("whatsapp"),"LinkedIn" to profile.text("linkedin"),"GitHub" to profile.text("github"),"Portfólio" to "https://karenangelis.com")) { (label,url) ->
                                OutlinedButton(onClick={visit(url)},modifier=Modifier.fillMaxWidth()) { Text(label) }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun EntryCard(title: String,subtitle: String,description: String) {
    Card(Modifier.fillMaxWidth(),colors=CardDefaults.cardColors(containerColor=Panel)) {
        Column(Modifier.padding(18.dp),verticalArrangement=Arrangement.spacedBy(10.dp)) {
            Text(title,fontSize=19.sp,fontWeight=FontWeight.Bold)
            if(subtitle.isNotEmpty()) Text(subtitle,fontSize=12.sp,color=Lime)
            if(description.isNotEmpty()) Text(description,fontSize=13.sp,color=Muted)
        }
    }
}

@Composable
private fun ExpandCard(title: String,initiallyOpen: Boolean=false,content: @Composable ColumnScope.()->Unit) {
    var expanded by remember { mutableStateOf(initiallyOpen) }
    Card(Modifier.fillMaxWidth(),colors=CardDefaults.cardColors(containerColor=Panel)) {
        Column(Modifier.padding(8.dp)) {
            TextButton(onClick={expanded=!expanded},modifier=Modifier.fillMaxWidth()) { Text(title,modifier=Modifier.weight(1f),fontSize=14.sp);Text(if(expanded) "−" else "+") }
            if(expanded) Column(Modifier.padding(10.dp),verticalArrangement=Arrangement.spacedBy(12.dp),content=content)
        }
    }
}
