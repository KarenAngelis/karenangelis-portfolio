@file:OptIn(ExperimentalLayoutApi::class)
package com.karenangelis.curriculo.shared

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.ScrollState
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.Orientation
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.draggable
import androidx.compose.foundation.gestures.rememberDraggableState
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.layout.positionInParent
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.serialization.json.JsonObject
import kotlin.math.roundToInt

private val Lime=Color(0xffc5f16a)
private val Ink=Color(0xff101211)
private val Panel=Color(0xff1c211b)
private val Raised=Color(0xff262d24)
private val Line=Color(0xff363c33)
private val Paper=Color(0xfff1f0e9)
private val Muted=Color(0xffa6aaa2)
private val CardShape=RoundedCornerShape(18.dp)

private class Tab(val label: String,val icon: ImageVector)
private val tabs=listOf(Tab("Início",AppIcons.Home),Tab("Habilidades",AppIcons.Skills),Tab("Experiência",AppIcons.Experience),Tab("Projetos",AppIcons.Projects),Tab("Contato",AppIcons.Contact))
private val categories=listOf("all" to "Todos","fullstack" to "Full Stack","backend" to "Backend","frontend" to "Frontend","data" to "Dados")

private data class ResumeState(
    val profile: JsonObject=parseProfile(BundledProfile.json),
    val selected: Int=0,
    val query: String="",
    val area: String="",
    val category: String="all",
    val status: String="Currículo incluído no app",
    val online: Boolean=false,
    val busy: Boolean=false
)

@Composable
fun ResumeApp() {
    MaterialTheme(colorScheme=darkColorScheme(primary=Lime,onPrimary=Ink,secondaryContainer=Lime.copy(alpha=.16f),onSecondaryContainer=Lime,background=Ink,surface=Panel,surfaceVariant=Raised,onSurface=Paper,onSurfaceVariant=Muted,outline=Line,outlineVariant=Line)) {
        var appState by remember { mutableStateOf(ResumeState()) }
        val profile=remember(appState.profile) { localizeProfile(appState.profile) }
        val scope=rememberCoroutineScope()
        val open=LocalUriHandler.current
        fun update() {
            if(appState.busy)return
            appState=appState.copy(busy=true,status="Atualizando currículo…")
            scope.launch {
                try {
                    val updated=withTimeout(12000) { fetchProfile() }
                    appState=appState.copy(profile=updated,status="Atualizado pela API Go",online=true,busy=false)
                    println("Resume profile refreshed from Go API")
                } catch(_: TimeoutCancellationException) {
                    appState=appState.copy(status="Sem conexão · usando currículo incluído no app",online=false,busy=false)
                } catch(e: CancellationException) { throw e }
                // Throwable, não Exception: no navegador o Ktor lança kotlin.Error quando a rede falha, e sem capturá-lo a tela travava.
                catch(e: Throwable) {
                    println("Profile update failed: ${e.message}")
                    appState=appState.copy(status="Sem conexão · usando currículo incluído no app",online=false,busy=false)
                }
            }
        }
        LaunchedEffect(Unit) { update() }
        fun visit(url: String) {
            val target=if(url.startsWith("/")) "https://karenangelis.com$url" else url
            if(target.startsWith("https://")) open.openUri(target)
        }
        Scaffold(
            containerColor=Ink,
            topBar={ TopBar(tr(tabs[appState.selected].label),appState.busy) { update() } },
            bottomBar={
                NavigationBar(containerColor=Panel,tonalElevation=0.dp) {
                    tabs.forEachIndexed { index,tab ->
                        NavigationBarItem(
                            selected=appState.selected==index,
                            onClick={appState=appState.copy(selected=index)},
                            icon={Icon(tab.icon,contentDescription=null,modifier=Modifier.size(22.dp))},
                            label={Text(tr(tab.label),fontSize=10.5.sp,maxLines=1,softWrap=false)},
                            colors=NavigationBarItemDefaults.colors(selectedIconColor=Lime,selectedTextColor=Lime,indicatorColor=Lime.copy(alpha=.14f),unselectedIconColor=Muted,unselectedTextColor=Muted)
                        )
                    }
                }
            }
        ) { padding ->
            AnimatedContent(
                targetState=appState.selected,
                modifier=Modifier.fillMaxSize().padding(padding),
                transitionSpec={
                    val direction=if(targetState>initialState) 1 else -1
                    (slideInHorizontally(tween(220)) { it/8*direction }+fadeIn(tween(220))) togetherWith (slideOutHorizontally(tween(160)) { -it/8*direction }+fadeOut(tween(120)))
                },
                label="tab"
            ) { tab ->
                when(tab) {
                    0 -> HomeScreen(profile,appState.status,appState.online,{appState=appState.copy(selected=it)},::visit)
                    1 -> SkillsScreen(profile,appState.query,appState.area,{appState=appState.copy(query=it)},{appState=appState.copy(area=it)},::visit)
                    2 -> ExperienceScreen(profile)
                    3 -> ProjectsScreen(profile,appState.category,{appState=appState.copy(category=it)},::visit)
                    else -> ContactScreen(profile,::visit)
                }
            }
        }
    }
}

@Composable
private fun TopBar(title: String,busy: Boolean,onRefresh: ()->Unit) {
    Surface(color=Ink) {
        Row(Modifier.fillMaxWidth().statusBarsPadding().padding(start=18.dp,end=8.dp,top=10.dp,bottom=8.dp),verticalAlignment=Alignment.CenterVertically) {
            Box(Modifier.size(36.dp).clip(RoundedCornerShape(11.dp)).background(Lime),contentAlignment=Alignment.Center) { Text("ka",color=Ink,fontSize=17.sp,fontWeight=FontWeight.Bold) }
            Column(Modifier.weight(1f).padding(start=12.dp)) {
                Text(title,fontSize=20.sp,fontWeight=FontWeight.Bold,color=Paper,maxLines=1)
                Text("Karen Angelis",fontSize=11.sp,color=Muted)
            }
            IconButton(onClick=onRefresh,enabled=!busy) {
                if(busy) CircularProgressIndicator(Modifier.size(18.dp),color=Lime,strokeWidth=2.dp)
                else Icon(AppIcons.Refresh,contentDescription=tr("Atualizar"),tint=Muted,modifier=Modifier.size(21.dp))
            }
        }
    }
}

@Composable
private fun HomeScreen(profile: JsonObject,status: String,online: Boolean,onTab: (Int)->Unit,visit: (String)->Unit) {
    val scroll=rememberScrollState()
    val scope=rememberCoroutineScope()
    // Posição de cada seção dentro da tela: os atalhos rolam até ela.
    val anchors=remember { mutableStateMapOf<String,Int>() }
    fun anchor(name: String)=Modifier.onGloballyPositioned { anchors[name]=it.positionInParent().y.roundToInt() }
    Screen(scroll) {
        Card(Modifier.fillMaxWidth(),shape=CardShape,colors=CardDefaults.cardColors(containerColor=Panel)) {
            Row(Modifier.padding(18.dp),verticalAlignment=Alignment.CenterVertically) {
                Box(Modifier.size(64.dp).clip(CircleShape).background(Lime),contentAlignment=Alignment.Center) {
                    Text(profile.text("name").split(" ").mapNotNull { it.firstOrNull() }.take(2).joinToString(""),color=Ink,fontSize=24.sp,fontWeight=FontWeight.Bold)
                }
                Column(Modifier.padding(start=16.dp),verticalArrangement=Arrangement.spacedBy(5.dp)) {
                    Text(profile.text("fullName"),fontSize=19.sp,fontWeight=FontWeight.Bold,lineHeight=23.sp)
                    Text(profile.text("role"),fontSize=12.5.sp,color=Muted,lineHeight=17.sp)
                    Row(verticalAlignment=Alignment.CenterVertically) {
                        Box(Modifier.size(7.dp).clip(CircleShape).background(if(online) Lime else Muted))
                        Text(tr(status),Modifier.padding(start=7.dp),fontSize=11.sp,lineHeight=15.sp,color=if(online) Lime else Muted)
                    }
                }
            }
        }
        Row(horizontalArrangement=Arrangement.spacedBy(10.dp)) {
            Button(onClick={visit(profile.text("whatsapp"))},modifier=Modifier.weight(1f).height(46.dp),contentPadding=PaddingValues(horizontal=8.dp)) { Text("WhatsApp",fontSize=13.sp,fontWeight=FontWeight.Bold,maxLines=1) }
            OutlinedButton(onClick={visit(profile.text("linkedin"))},modifier=Modifier.weight(1f).height(46.dp),contentPadding=PaddingValues(horizontal=8.dp)) { Text("LinkedIn",fontSize=13.sp,maxLines=1) }
            OutlinedButton(onClick={visit(profile.text("github"))},modifier=Modifier.weight(1f).height(46.dp),contentPadding=PaddingValues(horizontal=8.dp)) { Text("GitHub",fontSize=13.sp,maxLines=1) }
        }
        Row(horizontalArrangement=Arrangement.spacedBy(10.dp)) {
            StatTile(profile.rows("skillGroups").size.toString(),tr("áreas"),Modifier.weight(1f)) { onTab(1) }
            StatTile(profile.strings("skills").size.toString(),tr("competências"),Modifier.weight(1.25f)) { onTab(1) }
            StatTile(profile.rows("projects").size.toString(),tr("projetos"),Modifier.weight(1f)) { onTab(3) }
        }
        FlowRow(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
            listOf("Formação","Idiomas","Cursos e certificados").forEach { label ->
                AssistChip(onClick={anchors[label]?.let { target -> scope.launch { scroll.animateScrollTo(target) } }},label={Text(tr(label),fontSize=12.5.sp)})
            }
        }
        Card(Modifier.fillMaxWidth(),shape=CardShape,colors=CardDefaults.cardColors(containerColor=Panel)) {
            Column(Modifier.padding(18.dp),verticalArrangement=Arrangement.spacedBy(10.dp)) {
                SectionTitle(tr("Sobre mim"))
                Text(profile.text("summary"),fontSize=13.5.sp,color=Muted,lineHeight=21.sp)
            }
        }
        Column(anchor("Formação"),verticalArrangement=Arrangement.spacedBy(10.dp)) {
            SectionTitle(tr("Formação"))
            profile.rows("education").forEach { EntryCard(it.text("title"),it.text("institution")+" · "+it.text("status"),it.text("detail")) }
        }
        Column(anchor("Idiomas"),verticalArrangement=Arrangement.spacedBy(10.dp)) {
            SectionTitle(tr("Idiomas"))
            Card(Modifier.fillMaxWidth(),shape=CardShape,colors=CardDefaults.cardColors(containerColor=Panel)) {
                Column(Modifier.padding(horizontal=18.dp,vertical=6.dp)) {
                    val languages=profile.rows("languages")
                    languages.forEachIndexed { index,language ->
                        Column(Modifier.padding(vertical=12.dp),verticalArrangement=Arrangement.spacedBy(3.dp)) {
                            Text(language.text("name"),fontSize=15.sp,fontWeight=FontWeight.Bold)
                            Text(language.text("level"),fontSize=12.5.sp,color=Muted,lineHeight=17.sp)
                        }
                        if(index<languages.lastIndex) HorizontalDivider(color=Line)
                    }
                }
            }
        }
        Box(anchor("Cursos e certificados")) {
            val courses=profile.rows("courses")
            ExpandCard(tr("Cursos e certificados"),courses.size.toString(),true) {
                courses.forEach { course ->
                    Column(verticalArrangement=Arrangement.spacedBy(2.dp)) {
                        Text(course.text("title"),fontSize=14.sp,fontWeight=FontWeight.Bold,lineHeight=19.sp)
                        Text(course.text("institution")+" · "+course.text("detail"),fontSize=12.sp,color=Muted,lineHeight=17.sp)
                    }
                }
            }
        }
        val studies=profile.strings("additionalStudies")
        ExpandCard(tr("Outros estudos registrados"),studies.size.toString()) { studies.forEach { Text(it,fontSize=13.sp,color=Muted,lineHeight=19.sp) } }
    }
}

@Composable
private fun SkillsScreen(profile: JsonObject,query: String,area: String,onQuery: (String)->Unit,onArea: (String)->Unit,visit: (String)->Unit) {
    val term=query.trim().lowercase()
    val all=profile.rows("skillGroups")
    val groups=all.filter { (area.isEmpty() || it.text("id")==area) && (term.isEmpty() || (it.text("title")+" "+it.text("description")+" "+it.text("example")+" "+it.strings("items").joinToString(" ")).lowercase().contains(term)) }
    Screen(padding=PaddingValues(vertical=18.dp),spacing=12.dp) {
        OutlinedTextField(
            value=query,onValueChange=onQuery,singleLine=true,shape=RoundedCornerShape(16.dp),
            placeholder={Text(tr("Buscar habilidade"),color=Muted)},
            leadingIcon={Icon(AppIcons.Search,contentDescription=null,tint=Muted,modifier=Modifier.size(20.dp))},
            trailingIcon={ if(query.isNotEmpty()) IconButton(onClick={onQuery("")}) { Icon(AppIcons.Close,contentDescription=tr("Limpar busca"),tint=Muted,modifier=Modifier.size(18.dp)) } },
            modifier=Modifier.fillMaxWidth().padding(horizontal=18.dp)
        )
        LazyRow(contentPadding=PaddingValues(horizontal=18.dp),horizontalArrangement=Arrangement.spacedBy(8.dp)) {
            item { Filter(tr("Todas"),area.isEmpty()) { onArea("") } }
            items(all,key={it.text("id")}) { group -> Filter(group.text("title"),area==group.text("id")) { onArea(if(area==group.text("id")) "" else group.text("id")) } }
        }
        if(groups.isEmpty()) Text(tr("Nenhuma habilidade encontrada. Tente outro termo."),Modifier.padding(horizontal=18.dp),color=Muted,fontSize=13.5.sp)
        groups.forEach { group ->
            key(group.text("id"),term,area) {
                Box(Modifier.padding(horizontal=18.dp)) {
                    ExpandCard(group.text("title"),group.strings("items").size.toString(),term.isNotEmpty() || area.isNotEmpty()) {
                        Text(group.text("description"),fontSize=13.sp,color=Muted,lineHeight=19.sp)
                        FlowRow(horizontalArrangement=Arrangement.spacedBy(7.dp),verticalArrangement=Arrangement.spacedBy(7.dp)) {
                            group.strings("items").forEach { Pill(it,term.isNotEmpty() && it.lowercase().contains(term)) }
                        }
                        Text(group.text("example"),fontSize=12.sp,color=Muted,lineHeight=17.sp)
                        LinkButton(group.text("demoLabel")) { visit(group.text("demoUrl")) }
                    }
                }
            }
        }
        Box(Modifier.padding(start=18.dp,end=18.dp,top=10.dp)) { SectionTitle(tr("Como eu trabalho")) }
        profile.rows("softSkills").forEach { Box(Modifier.padding(horizontal=18.dp)) { EntryCard(it.text("title"),"",it.text("example")) } }
    }
}

@Composable
private fun ExperienceScreen(profile: JsonObject) {
    val entries=profile.rows("experience")
    Screen(padding=PaddingValues(start=14.dp,end=18.dp,top=18.dp,bottom=18.dp),spacing=0.dp) {
        entries.forEachIndexed { index,entry ->
            // Linha do tempo: o ponto da experiência atual é preenchido e o traço liga uma entrada à seguinte.
            Row(Modifier.height(IntrinsicSize.Min)) {
                Column(Modifier.width(26.dp).fillMaxHeight(),horizontalAlignment=Alignment.CenterHorizontally) {
                    Spacer(Modifier.height(22.dp))
                    Box(Modifier.size(12.dp).clip(CircleShape).background(if(index==0) Lime else Ink).border(2.dp,if(index==0) Lime else Muted,CircleShape))
                    if(index<entries.lastIndex) Box(Modifier.padding(top=6.dp).width(2.dp).weight(1f).background(Line))
                }
                Column(Modifier.weight(1f).padding(start=8.dp,bottom=14.dp)) {
                    Card(Modifier.fillMaxWidth(),shape=CardShape,colors=CardDefaults.cardColors(containerColor=Panel)) {
                        Column(Modifier.padding(18.dp),verticalArrangement=Arrangement.spacedBy(7.dp)) {
                            Text(entry.text("period").uppercase(),fontSize=11.sp,color=Lime,fontWeight=FontWeight.Bold,letterSpacing=1.sp)
                            Text(entry.text("company"),fontSize=18.sp,fontWeight=FontWeight.Bold,lineHeight=23.sp)
                            Text(entry.text("role"),fontSize=13.sp,color=Paper,lineHeight=18.sp)
                            Text(entry.text("description"),fontSize=13.sp,color=Muted,lineHeight=20.sp)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun ProjectsScreen(profile: JsonObject,category: String,onCategory: (String)->Unit,visit: (String)->Unit) {
    val projects=profile.rows("projects").filter { category=="all" || it.text("category")==category }
    Screen(padding=PaddingValues(vertical=18.dp),spacing=12.dp) {
        LazyRow(contentPadding=PaddingValues(horizontal=18.dp),horizontalArrangement=Arrangement.spacedBy(8.dp)) {
            items(categories,key={it.first}) { (id,label) -> Filter(tr(label),category==id) { onCategory(id) } }
        }
        projects.forEach { project ->
            Card(Modifier.fillMaxWidth().padding(horizontal=18.dp),shape=CardShape,colors=CardDefaults.cardColors(containerColor=Panel)) {
                Column(Modifier.padding(18.dp),verticalArrangement=Arrangement.spacedBy(10.dp)) {
                    Pill(tr(categories.firstOrNull { it.first==project.text("category") }?.second ?: project.text("category")),true)
                    Text(project.text("name"),fontSize=19.sp,fontWeight=FontWeight.Bold)
                    Text(project.text("description"),fontSize=13.sp,color=Muted,lineHeight=20.sp)
                    LinkButton(project.text("linkLabel")) { visit(project.text("url")) }
                }
            }
        }
    }
}

@Composable
private fun ContactScreen(profile: JsonObject,visit: (String)->Unit) {
    Screen(spacing=12.dp) {
        Column(Modifier.padding(top=10.dp,bottom=10.dp),verticalArrangement=Arrangement.spacedBy(8.dp)) {
            Text(tr("Vamos construir algo?"),fontSize=28.sp,fontWeight=FontWeight.Bold,color=Lime,lineHeight=33.sp)
            Text(tr("Karen Denich de Angelis"),fontSize=15.sp)
            Text(profile.text("role"),fontSize=12.5.sp,color=Muted)
        }
        Button(onClick={visit(profile.text("whatsapp"))},modifier=Modifier.fillMaxWidth().height(54.dp),shape=RoundedCornerShape(16.dp)) {
            Text("WhatsApp",Modifier.weight(1f),fontSize=15.sp,fontWeight=FontWeight.Bold)
            Icon(AppIcons.Outward,contentDescription=null,modifier=Modifier.size(19.dp))
        }
        listOf("LinkedIn" to profile.text("linkedin"),"GitHub" to profile.text("github"),"Portfólio" to "https://karenangelis.com").forEach { (label,url) ->
            OutlinedButton(onClick={visit(url)},modifier=Modifier.fillMaxWidth().height(54.dp),shape=RoundedCornerShape(16.dp)) {
                Text(tr(label),Modifier.weight(1f),fontSize=15.sp,color=Paper)
                Icon(AppIcons.Outward,contentDescription=null,tint=Muted,modifier=Modifier.size(19.dp))
            }
        }
    }
}

// Tela rolável com barra de rolagem: o Compose para web não desenha a barra do navegador.
@Composable
private fun Screen(scroll: ScrollState=rememberScrollState(),padding: PaddingValues=PaddingValues(18.dp),spacing: Dp=14.dp,content: @Composable ColumnScope.()->Unit) {
    var viewport by remember { mutableStateOf(0) }
    Box(Modifier.fillMaxSize().onSizeChanged { viewport=it.height }) {
        Column(Modifier.fillMaxSize().verticalScroll(scroll).padding(padding),verticalArrangement=Arrangement.spacedBy(spacing),content=content)
        Scrollbar(scroll,viewport,Modifier.align(Alignment.TopEnd))
    }
}

// Barra à direita: arrastar move a tela na mesma proporção; clicar no trilho leva direto ao ponto.
@Composable
private fun Scrollbar(scroll: ScrollState,viewport: Int,modifier: Modifier) {
    val max=scroll.maxValue
    if(viewport<=0 || max<=0 || max==Int.MAX_VALUE) return
    val density=LocalDensity.current
    val thumb=(viewport.toFloat()*viewport/(viewport+max)).coerceAtLeast(with(density) { 44.dp.toPx() })
    val travel=(viewport-thumb).coerceAtLeast(1f)
    val drag=rememberDraggableState { delta -> scroll.dispatchRawDelta(delta*max/travel) }
    Box(modifier.fillMaxHeight().width(14.dp).pointerInput(max,viewport) { detectTapGestures { position -> scroll.dispatchRawDelta((position.y-thumb/2)/travel*max-scroll.value) } }) {
        Box(Modifier.offset { IntOffset(0,(travel*scroll.value/max).roundToInt()) }.width(14.dp).height(with(density) { thumb.toDp() }).draggable(drag,Orientation.Vertical),contentAlignment=Alignment.CenterEnd) {
            Box(Modifier.padding(end=3.dp).width(5.dp).fillMaxHeight().clip(RoundedCornerShape(50)).background(Muted.copy(alpha=.6f)))
        }
    }
}

@Composable
private fun SectionTitle(text: String) { Text(text,fontSize=17.sp,fontWeight=FontWeight.Bold,color=Lime) }

@Composable
private fun StatTile(value: String,label: String,modifier: Modifier,onClick: ()->Unit) {
    Card(onClick=onClick,modifier=modifier,shape=CardShape,colors=CardDefaults.cardColors(containerColor=Panel)) {
        Column(Modifier.padding(horizontal=13.dp,vertical=14.dp),verticalArrangement=Arrangement.spacedBy(2.dp)) {
            Text(value,fontSize=26.sp,fontWeight=FontWeight.Bold,color=Lime)
            Text(label,fontSize=11.sp,color=Muted,maxLines=1,overflow=TextOverflow.Ellipsis)
        }
    }
}

@Composable
private fun Filter(label: String,selected: Boolean,onClick: ()->Unit) {
    FilterChip(selected=selected,onClick=onClick,label={Text(label,fontSize=12.5.sp,maxLines=1)},shape=RoundedCornerShape(50),
        colors=FilterChipDefaults.filterChipColors(containerColor=Ink,labelColor=Muted,selectedContainerColor=Lime,selectedLabelColor=Ink))
}

@Composable
private fun Pill(text: String,highlight: Boolean=false) {
    Text(text,fontSize=12.sp,color=if(highlight) Lime else Paper,lineHeight=16.sp,
        modifier=Modifier.clip(RoundedCornerShape(9.dp)).background(if(highlight) Lime.copy(alpha=.13f) else Raised).padding(horizontal=10.dp,vertical=6.dp))
}

@Composable
private fun LinkButton(label: String,onClick: ()->Unit) {
    FilledTonalButton(onClick=onClick,contentPadding=PaddingValues(horizontal=16.dp,vertical=8.dp)) {
        Text(label,fontSize=13.sp)
        Icon(AppIcons.Outward,contentDescription=null,modifier=Modifier.padding(start=8.dp).size(16.dp))
    }
}

@Composable
private fun EntryCard(title: String,subtitle: String,description: String) {
    Card(Modifier.fillMaxWidth(),shape=CardShape,colors=CardDefaults.cardColors(containerColor=Panel)) {
        Column(Modifier.padding(18.dp),verticalArrangement=Arrangement.spacedBy(7.dp)) {
            Text(title,fontSize=16.sp,fontWeight=FontWeight.Bold,lineHeight=21.sp)
            if(subtitle.isNotEmpty()) Text(subtitle,fontSize=12.sp,color=Lime,lineHeight=17.sp)
            if(description.isNotEmpty()) Text(description,fontSize=13.sp,color=Muted,lineHeight=19.sp)
        }
    }
}

@Composable
private fun ExpandCard(title: String,count: String,initiallyOpen: Boolean=false,content: @Composable ColumnScope.()->Unit) {
    var expanded by remember { mutableStateOf(initiallyOpen) }
    val turn by animateFloatAsState(if(expanded) 180f else 0f)
    Card(Modifier.fillMaxWidth(),shape=CardShape,colors=CardDefaults.cardColors(containerColor=Panel)) {
        Column {
            Row(Modifier.fillMaxWidth().clickable { expanded=!expanded }.padding(horizontal=18.dp,vertical=16.dp),verticalAlignment=Alignment.CenterVertically) {
                Text(title,Modifier.weight(1f),fontSize=15.sp,fontWeight=FontWeight.Bold,lineHeight=20.sp)
                Text(count,Modifier.padding(horizontal=10.dp).clip(RoundedCornerShape(50)).background(Raised).padding(horizontal=9.dp,vertical=3.dp),fontSize=11.5.sp,color=Lime)
                Icon(AppIcons.Chevron,contentDescription=null,tint=Muted,modifier=Modifier.size(20.dp).rotate(turn))
            }
            AnimatedVisibility(expanded) {
                Column(Modifier.padding(start=18.dp,end=18.dp,bottom=18.dp),verticalArrangement=Arrangement.spacedBy(12.dp),content=content)
            }
        }
    }
}
