package com.karenangelis.curriculo.shared

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.PathBuilder
import androidx.compose.ui.graphics.vector.path
import androidx.compose.ui.unit.dp

private fun icon(name: String, draw: PathBuilder.()->Unit): ImageVector =
    ImageVector.Builder(name=name,defaultWidth=24.dp,defaultHeight=24.dp,viewportWidth=24f,viewportHeight=24f).apply {
        path(fill=null,stroke=SolidColor(Color.White),strokeLineWidth=1.8f,strokeLineCap=StrokeCap.Round,strokeLineJoin=StrokeJoin.Round,pathBuilder=draw)
    }.build()

// Ícones desenhados à mão para não carregar a biblioteca de ícones inteira no WebAssembly.
internal object AppIcons {
    val Home=icon("Home") {
        moveTo(3f,11f);lineTo(12f,3f);lineTo(21f,11f)
        moveTo(5f,10f);lineTo(5f,21f);lineTo(19f,21f);lineTo(19f,10f)
        moveTo(10f,21f);lineTo(10f,14f);lineTo(14f,14f);lineTo(14f,21f)
    }
    val Skills=icon("Skills") {
        moveTo(3f,3f);lineTo(9f,3f);lineTo(9f,9f);lineTo(3f,9f);close()
        moveTo(15f,3f);lineTo(21f,3f);lineTo(21f,9f);lineTo(15f,9f);close()
        moveTo(3f,15f);lineTo(9f,15f);lineTo(9f,21f);lineTo(3f,21f);close()
        moveTo(15f,15f);lineTo(21f,15f);lineTo(21f,21f);lineTo(15f,21f);close()
    }
    val Experience=icon("Experience") {
        moveTo(3f,7f);lineTo(21f,7f);lineTo(21f,20f);lineTo(3f,20f);close()
        moveTo(8f,7f);lineTo(8f,3f);lineTo(16f,3f);lineTo(16f,7f)
        moveTo(3f,12f);lineTo(10f,12f);lineTo(10f,15f);lineTo(14f,15f);lineTo(14f,12f);lineTo(21f,12f)
    }
    val Projects=icon("Projects") {
        moveTo(8f,6f);lineTo(2f,12f);lineTo(8f,18f)
        moveTo(16f,6f);lineTo(22f,12f);lineTo(16f,18f)
        moveTo(14f,3f);lineTo(10f,21f)
    }
    val Contact=icon("Contact") {
        moveTo(4f,4f);lineTo(20f,4f);lineTo(20f,17f);lineTo(11f,17f);lineTo(5f,21f);lineTo(5f,17f);lineTo(4f,17f);close()
        moveTo(8f,9f);lineTo(16f,9f);moveTo(8f,13f);lineTo(13f,13f)
    }
    val Search=icon("Search") {
        moveTo(18f,11f);curveTo(18f,14.87f,14.87f,18f,11f,18f);curveTo(7.13f,18f,4f,14.87f,4f,11f)
        curveTo(4f,7.13f,7.13f,4f,11f,4f);curveTo(14.87f,4f,18f,7.13f,18f,11f);close()
        moveTo(16f,16f);lineTo(21f,21f)
    }
    val Close=icon("Close") { moveTo(6f,6f);lineTo(18f,18f);moveTo(18f,6f);lineTo(6f,18f) }
    val Refresh=icon("Refresh") {
        moveTo(20f,12f);curveTo(20f,16.42f,16.42f,20f,12f,20f);curveTo(7.58f,20f,4f,16.42f,4f,12f)
        curveTo(4f,7.58f,7.58f,4f,12f,4f);curveTo(14.5f,4f,16.7f,5.1f,18.2f,6.9f)
        moveTo(19f,3f);lineTo(19f,7.5f);lineTo(14.5f,7.5f)
    }
    val Outward=icon("Outward") { moveTo(7f,17f);lineTo(17f,7f);moveTo(9f,7f);lineTo(17f,7f);lineTo(17f,15f) }
    val Chevron=icon("Chevron") { moveTo(6f,9f);lineTo(12f,15f);lineTo(18f,9f) }
}
