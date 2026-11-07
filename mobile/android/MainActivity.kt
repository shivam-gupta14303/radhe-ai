package com.radhe.assistant

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.Send
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {

    private lateinit var voiceRecorder: VoiceRecorder

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        voiceRecorder = VoiceRecorder(this)

        setContent {
            RadheAppTheme {
                RadheCompanionScreen(
                    onStartVoice = { voiceRecorder.startRecording() },
                    onStopVoice = { voiceRecorder.stopRecording() }
                )
            }
        }
    }
}

@Composable
fun RadheAppTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colors = darkColors(
            primary = Color(0xFF6C5CE7),
            background = Color(0xFF0F172A),
            surface = Color(0xFF1E293B),
            onPrimary = Color.White,
            onBackground = Color(0xFFE2E8F0),
            onSurface = Color(0xFFE2E8F0)
        ),
        content = content
    )
}

@Composable
fun RadheCompanionScreen(
    onStartVoice: () -> Unit,
    onStopVoice: () -> Unit
) {
    var isRecording by remember { mutableStateOf(false) }
    var chatInput by remember { mutableStateOf("") }
    var conversationLog by remember { mutableStateOf(listOf("Radhe: Namaste! How can I help you today?")) }
    val coroutineScope = rememberCoroutineScope()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Radhe AI Companion", fontWeight = FontWeight.Bold) },
                backgroundColor = MaterialTheme.colors.surface,
                elevation = 4.dp
            )
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .background(MaterialTheme.colors.background)
                .padding(16.dp),
            verticalArrangement = Arrangement.SpaceBetween
        ) {
            // 1. Briefing & WhatsApp Approvals Banner
            Card(
                shape = RoundedCornerShape(12.dp),
                backgroundColor = MaterialTheme.colors.surface,
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text("Daily Briefing", fontSize = 16.sp, fontWeight = FontWeight.Bold, color = Color(0xFFA29BFE))
                    Spacer(modifier = Modifier.height(4.dp))
                    Text("Your calendar is open today. Hydration goal: 2500ml.", fontSize = 14.sp)
                }
            }

            Spacer(modifier = Modifier.height(12.dp))

            // 2. Chat Log
            Card(
                shape = RoundedCornerShape(12.dp),
                backgroundColor = MaterialTheme.colors.surface,
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(1f)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    for (msg in conversationLog) {
                        Text(msg, fontSize = 14.sp, modifier = Modifier.padding(vertical = 4.dp))
                    }
                }
            }

            Spacer(modifier = Modifier.height(12.dp))

            // 3. Voice & Input Bar
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically
            ) {
                TextField(
                    value = chatInput,
                    onValueChange = { chatInput = it },
                    placeholder = { Text("Ask Radhe anything...") },
                    modifier = Modifier.weight(1f),
                    shape = RoundedCornerShape(24.dp),
                    colors = TextFieldDefaults.textFieldColors(
                        backgroundColor = MaterialTheme.colors.surface,
                        focusedIndicatorColor = Color.Transparent,
                        unfocusedIndicatorColor = Color.Transparent
                    )
                )

                Spacer(modifier = Modifier.width(8.dp))

                // Mic / Push-to-Talk Button
                FloatingActionButton(
                    onClick = {
                        if (!isRecording) {
                            onStartVoice()
                            isRecording = true
                        } else {
                            onStopVoice()
                            isRecording = false
                            conversationLog = conversationLog + "You: [Voice Command Sent]"
                        }
                    },
                    backgroundColor = if (isRecording) Color(0xFFFF7675) else MaterialTheme.colors.primary,
                    shape = CircleShape
                ) {
                    Icon(Icons.Default.Mic, contentDescription = "Voice Input", tint = Color.White)
                }
            }
        }
    }
}
