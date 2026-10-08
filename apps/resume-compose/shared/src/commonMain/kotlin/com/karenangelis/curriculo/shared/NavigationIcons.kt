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

internal val NavigationIcons=listOf(
    icon("Skills") {
        moveTo(3f,3f);lineTo(9f,3f);lineTo(9f,9f);lineTo(3f,9f);close()
        moveTo(15f,3f);lineTo(21f,3f);lineTo(21f,9f);lineTo(15f,9f);close()
        moveTo(3f,15f);lineTo(9f,15f);lineTo(9f,21f);lineTo(3f,21f);close()
        moveTo(15f,15f);lineTo(21f,15f);lineTo(21f,21f);lineTo(15f,21f);close()
    },
    icon("Experience") {
        moveTo(3f,7f);lineTo(21f,7f);lineTo(21f,20f);lineTo(3f,20f);close()
        moveTo(8f,7f);lineTo(8f,3f);lineTo(16f,3f);lineTo(16f,7f)
        moveTo(3f,12f);lineTo(10f,12f);lineTo(10f,15f);lineTo(14f,15f);lineTo(14f,12f);lineTo(21f,12f)
    },
    icon("Education") {
        moveTo(12f,5f);curveTo(9f,3f,6f,3f,2f,4f);lineTo(2f,19f);curveTo(6f,18f,9f,18f,12f,21f)
        curveTo(15f,18f,18f,18f,22f,19f);lineTo(22f,4f);curveTo(18f,3f,15f,3f,12f,5f);lineTo(12f,21f)
    },
    icon("Languages") {
        moveTo(21f,12f);curveTo(21f,17f,17f,21f,12f,21f);curveTo(7f,21f,3f,17f,3f,12f)
        curveTo(3f,7f,7f,3f,12f,3f);curveTo(17f,3f,21f,7f,21f,12f);close()
        moveTo(3f,12f);lineTo(21f,12f)
        moveTo(12f,3f);curveTo(7f,8f,7f,16f,12f,21f);curveTo(17f,16f,17f,8f,12f,3f)
    },
    icon("Projects") {
        moveTo(8f,6f);lineTo(2f,12f);lineTo(8f,18f)
        moveTo(16f,6f);lineTo(22f,12f);lineTo(16f,18f)
        moveTo(14f,3f);lineTo(10f,21f)
    },
    icon("Contact") {
        moveTo(4f,4f);lineTo(20f,4f);lineTo(20f,17f);lineTo(11f,17f);lineTo(5f,21f);lineTo(5f,17f);lineTo(4f,17f);close()
        moveTo(8f,9f);lineTo(16f,9f);moveTo(8f,13f);lineTo(13f,13f)
    }
)
