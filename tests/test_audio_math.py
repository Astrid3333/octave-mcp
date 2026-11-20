"""Pruebas de regresion del tool audio_math_tool (matematica de audio)."""

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import audio_math_tool  # noqa: E402


class AudioMathTests(unittest.TestCase):
    def test_rms_db_matches_analytic(self):
        result = audio_math_tool.rms_db({"signal": [0.5] * 1000, "fs": 48000})
        self.assertAlmostEqual(result["rms_dbfs"], -6.020599913279624, places=9)

    def test_lufs_matches_ffmpeg_ebur128(self):
        fs = 48000
        time = np.arange(fs * 2) / fs
        amplitude = 10.0 ** (-23.0 / 20.0)
        signal = amplitude * np.sin(2.0 * np.pi * 1000.0 * time)
        result = audio_math_tool.lufs_kweight({"signal": signal, "fs": fs})
        self.assertAlmostEqual(result["integrated_lufs"], -26.0, delta=0.2)

    def test_true_peak_detects_inter_sample_peak(self):
        fs = 48000
        samples = np.zeros(fs)
        samples[100] = 0.9
        samples[101] = -0.9
        result = audio_math_tool.true_peak({"signal": samples, "fs": fs})
        self.assertGreater(result["true_peak"], 0.9)
        self.assertLessEqual(result["true_peak"], 1.0)

    def test_fft_finds_dominant_frequency(self):
        fs = 48000
        time = np.arange(fs) / fs
        signal = np.sin(2.0 * np.pi * 1000.0 * time)
        result = audio_math_tool.fft_spectrum({"signal": signal, "fs": fs})
        self.assertAlmostEqual(result["dominant_frequency_hz"], 1000.0, delta=1.0)

    def test_convolve_identity_and_delay(self):
        signal = np.sin(2.0 * np.pi * 100.0 * np.arange(512) / 48000.0)
        identity = audio_math_tool.convolve_ir(
            {"signal": signal, "ir": [1.0], "mode": "full"}
        )
        np.testing.assert_allclose(identity["signal"], signal, atol=1e-12)
        delayed = audio_math_tool.convolve_ir(
            {"signal": signal, "ir": [0.0, 0.0, 1.0], "mode": "full"}
        )
        expected = np.zeros(len(signal) + 2)
        expected[2:] = signal
        np.testing.assert_allclose(delayed["signal"], expected, atol=1e-12)

    def test_spectral_subtract_improves_snr(self):
        fs = 48000
        rng = np.random.default_rng(42)
        noise = rng.normal(0.0, 0.02, 8192)
        tone = 0.25 * np.sin(2.0 * np.pi * 1000.0 * np.arange(8192) / fs)
        noisy = np.concatenate([noise[:4096], tone[:4096] + noise[4096:]])
        result = audio_math_tool.spectral_subtract({"signal": noisy, "fs": fs})
        self.assertIsNotNone(result["snr_improvement_db"])
        self.assertGreater(result["snr_improvement_db"], 0.0)

    def test_ducking_reduces_gain_when_control_is_active(self):
        fs = 48000
        control = np.concatenate([np.zeros(fs // 2), np.ones(fs // 2)])
        result = audio_math_tool.ducking_gain(
            {"signal": np.ones(fs), "control": control, "fs": fs}
        )
        active = np.mean(result["gain_db"][int(fs * 0.7):int(fs * 0.9)])
        self.assertLess(active, -5.0)

    def test_silence_detection_reports_pause(self):
        signal = np.concatenate([np.ones(1000), np.zeros(2000), np.ones(1000)])
        result = audio_math_tool.silence_samples(
            {"signal": signal, "fs": 48000, "minimum_duration_ms": 10.0}
        )
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["pauses"][0]["n_samples"], 2000)

    def test_silence_detection_works_with_room_noise(self):
        # Pausa 1 s de ruido a -60 dBFS dentro de un ruido de sala a -45 dBFS:
        # el criterio por pico no la ve (los picos del ruido perforan el umbral)
        # y el criterio de nivel por trama si.
        fs = 48000
        rng = np.random.default_rng(5)
        sala = rng.normal(0.0, 10.0 ** (-45.0 / 20.0), fs)
        pausa = rng.normal(0.0, 10.0 ** (-60.0 / 20.0), fs)
        senal = np.concatenate([sala, pausa, sala])
        por_nivel = audio_math_tool.silence_samples(
            {"signal": senal, "fs": fs, "threshold_dbfs": -50.0, "minimum_duration_ms": 400.0}
        )
        self.assertEqual(por_nivel["count"], 1)
        self.assertAlmostEqual(por_nivel["pauses"][0]["duration_seconds"], 1.0, delta=0.05)
        por_pico = audio_math_tool.silence_samples(
            {
                "signal": senal,
                "fs": fs,
                "threshold_dbfs": -50.0,
                "minimum_duration_ms": 400.0,
                "metrica": "pico",
            }
        )
        self.assertEqual(por_pico["count"], 0)

    def test_diagnostico_detects_clipping_and_click(self):
        signal = np.concatenate([np.full(1000, 0.1), np.array([1.0, 1.0, -1.0, -1.0])])
        result = audio_math_tool.diagnostico_toma({"signal": signal, "fs": 48000})
        self.assertEqual(result["clipped_samples"], 4)
        self.assertGreaterEqual(result["click_count"], 1)

    def test_diagnostico_no_reporta_clics_en_senal_limpia(self):
        # Voz sintetica: fundamental suave y rafagas fricativas de ruido con
        # envolvente coseno (sin ninguna discontinuidad). Reproduce el perfil
        # del habla real: saltos entre muestras pequenos en mediana (0.0015) con
        # picos de 0.25. El criterio antiguo por salto absoluto marcaba aqui
        # cientos de falsos positivos.
        fs = 48000
        n = fs
        time = np.arange(n) / fs
        rng = np.random.default_rng(11)
        signal = 0.20 * np.sin(2.0 * np.pi * 180.0 * time) + 0.05 * np.sin(2.0 * np.pi * 540.0 * time)
        for inicio in (0.15, 0.35, 0.55, 0.75):
            duracion = int(0.02 * fs)
            muestras = int(inicio * fs)
            envolvente = 0.5 * (1.0 - np.cos(2.0 * np.pi * np.arange(duracion) / duracion))
            ruido = rng.normal(0.0, 1.0, duracion)
            ruido = np.convolve(ruido, np.ones(4) / 4.0, mode="same")
            signal[muestras:muestras + duracion] += (
                0.30 * envolvente * ruido / np.max(np.abs(ruido))
            )
        saltos = np.abs(np.diff(signal))
        self.assertLess(float(np.median(saltos)), 0.01)
        self.assertGreater(float(np.max(saltos)), 0.05)
        result = audio_math_tool.diagnostico_toma({"signal": signal, "fs": fs})
        self.assertEqual(result["click_count"], 0)

    def test_diagnostico_cuenta_cada_transitorio_una_vez(self):
        fs = 48000
        time = np.arange(fs) / fs
        signal = 0.3 * np.sin(2.0 * np.pi * 220.0 * time)
        burst = int(0.0005 * fs)
        for inicio in (int(0.3 * fs), int(0.5 * fs), int(0.7 * fs)):
            signal[inicio:inicio + burst] += 0.8
        result = audio_math_tool.diagnostico_toma({"signal": signal, "fs": fs})
        self.assertEqual(result["click_count"], 3)

    def test_diagnostico_ignora_ruido_de_suelo_pero_detecta_un_clic_en_silencio(self):
        fs = 48000
        suelo = np.random.default_rng(3).normal(0.0, 1e-5, fs)
        sin_clic = audio_math_tool.diagnostico_toma({"signal": suelo, "fs": fs})
        self.assertEqual(sin_clic["click_count"], 0)
        con_clic = suelo.copy()
        con_clic[int(0.5 * fs)] += 0.05
        resultado = audio_math_tool.diagnostico_toma({"signal": con_clic, "fs": fs})
        self.assertEqual(resultado["click_count"], 1)

    def test_multicanal_acepta_canales_por_muestras(self):
        fs = 48000
        time = np.arange(fs) / fs
        izquierda = 0.2 * np.sin(2.0 * np.pi * 1000.0 * time)
        derecha = 0.1 * np.sin(2.0 * np.pi * 1000.0 * time)
        stereo = np.vstack([izquierda, derecha])
        resultado = audio_math_tool.rms_db({"signal": stereo, "fs": fs})
        esperado = 20.0 * np.log10(np.sqrt(np.mean(np.square(stereo))))
        self.assertAlmostEqual(resultado["rms_dbfs"], esperado, delta=1e-6)

    def test_multicanal_acepta_muestras_por_canales(self):
        fs = 48000
        time = np.arange(fs) / fs
        izquierda = 0.2 * np.sin(2.0 * np.pi * 1000.0 * time)
        derecha = 0.1 * np.sin(2.0 * np.pi * 1000.0 * time)
        transposition = np.vstack([izquierda, derecha]).T
        resultado = audio_math_tool.rms_db({"signal": transposition, "fs": fs})
        esperado = 20.0 * np.log10(np.sqrt(np.mean(np.square(transposition.T))))
        self.assertAlmostEqual(resultado["rms_dbfs"], esperado, delta=1e-6)

    def test_validate_passes(self):
        result = audio_math_tool.validate()
        failed = [check["name"] for check in result["checks"] if not check["passed"]]
        self.assertEqual(failed, [])
        self.assertTrue(result["validation_passed"])

    def test_tool_is_registered(self):
        import tool_registry

        self.assertIn("audio_math_tool", tool_registry.get_names())
        schema = tool_registry.get_schema("audio_math_tool")
        self.assertEqual(schema["name"], "audio_math_tool")
        modes = schema["inputSchema"]["properties"]["mode"]["enum"]
        self.assertIn("diagnostico_toma", modes)


if __name__ == "__main__":
    unittest.main()
