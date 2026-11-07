package com.radhe.assistant

import android.content.Context
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import java.io.File
import java.io.FileOutputStream
import java.io.RandomAccessFile
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

class VoiceRecorder(private val context: Context) {

    private val sampleRate = 16000
    private val channelConfig = AudioFormat.CHANNEL_IN_MONO
    private val audioFormat = AudioFormat.ENCODING_PCM_16BIT
    private val bufferSize = AudioRecord.getMinBufferSize(sampleRate, channelConfig, audioFormat)

    private var audioRecord: AudioRecord? = null
    private var isRecording = false
    private var outputFile: File? = null

    fun startRecording(): File {
        val audioDir = File(context.cacheDir, "radhe_audio")
        if (!audioDir.exists()) audioDir.mkdirs()
        val pcmFile = File(audioDir, "temp_voice.pcm")
        outputFile = File(audioDir, "recorded_voice.wav")

        audioRecord = AudioRecord(
            MediaRecorder.AudioSource.MIC,
            sampleRate,
            channelConfig,
            audioFormat,
            bufferSize
        )

        audioRecord?.startRecording()
        isRecording = true

        Thread {
            val buffer = ByteArray(bufferSize)
            FileOutputStream(pcmFile).use { fos ->
                while (isRecording) {
                    val read = audioRecord?.read(buffer, 0, buffer.size) ?: 0
                    if (read > 0) {
                        fos.write(buffer, 0, read)
                    }
                }
            }
            writeWavHeader(pcmFile, outputFile!!)
        }.start()

        return outputFile!!
    }

    fun stopRecording(): File? {
        isRecording = false
        try {
            audioRecord?.stop()
            audioRecord?.release()
            audioRecord = null
        } catch (e: Exception) {
            e.printStackTrace()
        }
        return outputFile
    }

    private fun writeWavHeader(pcmFile: File, wavFile: File) {
        val pcmBytes = pcmFile.readBytes()
        val totalAudioLen = pcmBytes.size
        val totalDataLen = totalAudioLen + 36
        val channels = 1
        val byteRate = 16 * sampleRate * channels / 8

        RandomAccessFile(wavFile, "rw").use { raf ->
            raf.setLength(0) // Clear
            raf.writeBytes("RIFF")
            raf.writeInt(Integer.reverseBytes(totalDataLen))
            raf.writeBytes("WAVE")
            raf.writeBytes("fmt ")
            raf.writeInt(Integer.reverseBytes(16)) // 16 for PCM
            raf.writeShort(java.lang.Short.reverseBytes(1.toShort()).toInt()) // PCM format
            raf.writeShort(java.lang.Short.reverseBytes(channels.toShort()).toInt())
            raf.writeInt(Integer.reverseBytes(sampleRate))
            raf.writeInt(Integer.reverseBytes(byteRate))
            raf.writeShort(java.lang.Short.reverseBytes(2.toShort()).toInt()) // Block align
            raf.writeShort(java.lang.Short.reverseBytes(16.toShort()).toInt()) // Bits per sample
            raf.writeBytes("data")
            raf.writeInt(Integer.reverseBytes(totalAudioLen))
            raf.write(pcmBytes)
        }
    }
}
