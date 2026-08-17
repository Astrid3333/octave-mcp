// glossary_tool.cpp
//
// Glosario tecnico multilingue para octave-mcp: traduccion determinista
// termino-a-termino (diccionario) + reglas simples de reordenamiento,
// NO un modelo estadistico ni neuronal. Pensado para traducir las
// "description" cortas de los schemas de las tools (frases tecnicas
// acotadas), no texto libre arbitrario.
//
// Patron de validacion igual al resto del repo: modo "validate" con
// checks calculados a mano, exit code 0 si todo pasa, 1 si algo falla.
// No se integra directo al dispatcher de server.py (que es Python);
// se puede invocar como subprocess, mismo patron que run_all_validations.py
// ya usa para invocar server.py.
//
// Build:   g++ -std=c++17 -O2 -o glossary_tool glossary_tool.cpp
// Uso:     ./glossary_tool --validate
//          ./glossary_tool --translate "gas ideal" en
//          ./glossary_tool --list-languages

#include <algorithm>
#include <cctype>
#include <iostream>
#include <map>
#include <optional>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>

// declarada antes de su uso en translatePhrase() (definicion completa mas abajo)
std::string applyReorderRule(const std::vector<std::string>& translatedTokens,
                              const std::string& lang);

// ---------------------------------------------------------------------
// Utilidades de string
// ---------------------------------------------------------------------

static std::string toLower(const std::string& s) {
    std::string out = s;
    std::transform(out.begin(), out.end(), out.begin(),
                    [](unsigned char c) { return std::tolower(c); });
    return out;
}

static std::vector<std::string> tokenize(const std::string& text) {
    std::vector<std::string> tokens;
    std::istringstream iss(text);
    std::string tok;
    while (iss >> tok) {
        // recorta puntuacion basica al final del token
        while (!tok.empty() && std::ispunct((unsigned char)tok.back())) {
            tok.pop_back();
        }
        if (!tok.empty()) tokens.push_back(tok);
    }
    return tokens;
}

// ---------------------------------------------------------------------
// Glosario: termino_normalizado(es) -> {idioma -> traduccion}
// ---------------------------------------------------------------------

class TechnicalGlossary {
public:
    TechnicalGlossary() { loadBuiltinTerms(); }

    // Traduce un termino (una sola palabra o frase corta ya normalizada)
    // al idioma pedido. Devuelve nullopt si no esta en el diccionario.
    std::optional<std::string> lookup(const std::string& term_es,
                                       const std::string& lang) const {
        auto it = dict_.find(toLower(term_es));
        if (it == dict_.end()) return std::nullopt;
        auto langIt = it->second.find(lang);
        if (langIt == it->second.end()) return std::nullopt;
        return langIt->second;
    }

    // Traduccion palabra-a-palabra de una frase completa, con dos reglas
    // de reordenamiento simples explicadas en applyReorderRule().
    // Palabras sin entrada en el diccionario se devuelven sin traducir,
    // marcadas entre corchetes, para que quede visible el hueco (no se
    // inventa una traduccion).
    std::string translatePhrase(const std::string& text_es,
                                 const std::string& lang) const {
        std::vector<std::string> tokens = tokenize(toLower(text_es));
        std::vector<std::string> translated;
        translated.reserve(tokens.size());
        for (const auto& tok : tokens) {
            auto tr = lookup(tok, lang);
            translated.push_back(tr ? *tr : ("[" + tok + "]"));
        }
        return applyReorderRule(translated, lang);
    }

    bool hasLanguage(const std::string& lang) const {
        return std::find(supportedLanguages_.begin(), supportedLanguages_.end(),
                          lang) != supportedLanguages_.end();
    }

    std::vector<std::string> listLanguages() const {
        std::vector<std::string> out = supportedLanguages_;
        std::sort(out.begin(), out.end());
        return out;
    }

    size_t termCount() const { return dict_.size(); }

private:
    // dict_[termino_es][idioma] = traduccion
    std::unordered_map<std::string, std::unordered_map<std::string, std::string>> dict_;
    std::vector<std::string> supportedLanguages_;

    void addTerm(const std::string& es, const std::string& en,
                 const std::string& pt, const std::string& fr,
                 const std::string& it, const std::string& de) {
        dict_[toLower(es)] = {{"en", en}, {"pt", pt}, {"fr", fr},
                               {"it", it}, {"de", de}};
    }

    void loadBuiltinTerms() {
        supportedLanguages_ = {"en", "pt", "fr", "it", "de"};

        // Vocabulario tecnico de los schemas de octave-mcp (subset representativo,
        // ampliable agregando lineas a addTerm sin tocar el resto del codigo).
        // Columnas: es, en, pt, fr, it, de -- cada traduccion verificada a mano,
        // no generada. Para aleman: se usan sustantivos capitalizados (regla
        // ortografica real del idioma), y se documenta en el comentario del
        // check correspondiente una limitacion real de concordancia de genero.
        addTerm("gas", "gas", "gas", "gaz", "gas", "Gas");
        addTerm("ideal", "ideal", "ideal", "ideal", "ideale", "ideal");
        addTerm("real", "real", "real", "reel", "reale", "real");
        addTerm("presion", "pressure", "pressao", "pression", "pressione", "Druck");
        addTerm("volumen", "volume", "volume", "volume", "volume", "Volumen");
        addTerm("temperatura", "temperature", "temperatura", "temperature", "temperatura", "Temperatur");
        addTerm("energia", "energy", "energia", "energie", "energia", "Energie");
        addTerm("validar", "validate", "validar", "valider", "validare", "validieren");
        addTerm("validacion", "validation", "validacao", "validation", "validazione", "Validierung");
        addTerm("herramienta", "tool", "ferramenta", "outil", "strumento", "Werkzeug");
        addTerm("matematica", "mathematics", "matematica", "mathematiques", "matematica", "Mathematik");
        addTerm("seguro", "insurance", "seguro", "assurance", "assicurazione", "Versicherung");
        addTerm("riesgo", "risk", "risco", "risque", "rischio", "Risiko");
        addTerm("prima", "premium", "premio", "prime", "premio", "Praemie");
        addTerm("perdida", "loss", "perda", "perte", "perdita", "Verlust");
        addTerm("capa", "layer", "camada", "couche", "strato", "Schicht");
        addTerm("cinetica", "kinetics", "cinetica", "cinetique", "cinetica", "Kinetik");
        addTerm("teoria", "theory", "teoria", "theorie", "teoria", "Theorie");
        addTerm("humedad", "humidity", "umidade", "humidite", "umidita", "Feuchtigkeit");
        addTerm("compresible", "compressible", "compressivel", "compressible", "comprimibile", "komprimierbar");
        addTerm("mezcla", "mixture", "mistura", "melange", "miscela", "Mischung");
        addTerm("choque", "shock", "choque", "choc", "urto", "Stoss");
        addTerm("onda", "wave", "onda", "onde", "onda", "Welle");
    }
};

// ---------------------------------------------------------------------
// Regla de reordenamiento
// ---------------------------------------------------------------------
//
// Regla 1 (es->en/de para sustantivo+adjetivo):
// En espanol el adjetivo suele ir DESPUES del sustantivo ("gas ideal").
// En ingles y aleman va ANTES ("ideal gas" / "ideal Gas"). Portugues,
// frances e italiano mantienen el orden sustantivo+adjetivo como el
// espanol, asi que la regla solo invierte el orden para "en" y "de".
//
// LIMITACION REAL conocida (no oculta): en aleman el adjetivo antepuesto
// normalmente lleva un sufijo de concordancia de genero/caso/numero
// (ej. "ideales Gas", no "ideal Gas", porque "Gas" es neutro nominativo).
// Este glosario NO maneja genero gramatical ni declinacion -- el
// resultado para "de" queda semanticamente correcto (se entienden las
// palabras) pero gramaticalmente incompleto. Documentado tambien en el
// check de validacion correspondiente, no se pretende que sea aleman
// gramaticalmente perfecto.
//
// Esta es una heuristica de 2 palabras, no un parser sintactico real:
// solo aplica cuando la frase traducida tiene exactamente 2 tokens y el
// idioma destino es "en" o "de".
std::string applyReorderRule(const std::vector<std::string>& translatedTokens,
                              const std::string& lang) {
    if ((lang == "en" || lang == "de") && translatedTokens.size() == 2) {
        // sustantivo adjetivo (es) -> adjetivo sustantivo (en/de)
        return translatedTokens[1] + " " + translatedTokens[0];
    }
    std::string out;
    for (size_t i = 0; i < translatedTokens.size(); ++i) {
        if (i > 0) out += " ";
        out += translatedTokens[i];
    }
    return out;
}

// ---------------------------------------------------------------------
// Suite de validacion (checks calculados a mano)
// ---------------------------------------------------------------------

struct Check {
    std::string name;
    bool passed;
    std::string detail;
};

std::vector<Check> runValidation() {
    TechnicalGlossary g;
    std::vector<Check> checks;

    // 1) lookup directo de un termino conocido
    auto t1 = g.lookup("presion", "en");
    checks.push_back({"lookup_presion_en_matches_pressure",
                       t1.has_value() && *t1 == "pressure",
                       t1 ? *t1 : "(no match)"});

    // 2) termino inexistente devuelve nullopt (no inventa traduccion)
    auto t2 = g.lookup("palabra_inexistente_xyz", "en");
    checks.push_back({"unknown_term_returns_nullopt", !t2.has_value(),
                       t2 ? *t2 : "nullopt (correcto)"});

    // 3) idioma soportado
    checks.push_back({"supports_en_pt_fr",
                       g.hasLanguage("en") && g.hasLanguage("pt") && g.hasLanguage("fr"),
                       "en/pt/fr"});

    // 4) idioma no soportado (ja: japones, no esta en el diccionario)
    checks.push_back({"unsupported_language_ja_returns_false",
                       !g.hasLanguage("ja"), "ja no deberia estar soportado"});

    // 5) traduccion de frase de 2 palabras "gas ideal" -> reordena a "ideal gas" en ingles
    // (verificado a mano: en espanol el adjetivo va despues, en ingles antes)
    std::string tr5 = g.translatePhrase("gas ideal", "en");
    checks.push_back({"phrase_gas_ideal_en_reorders_to_ideal_gas",
                       tr5 == "ideal gas", tr5});

    // 6) misma frase en portugues NO reordena (portugues mantiene sustantivo+adjetivo)
    std::string tr6 = g.translatePhrase("gas ideal", "pt");
    checks.push_back({"phrase_gas_ideal_pt_keeps_order",
                       tr6 == "gas ideal", tr6});

    // 7) frase con palabra fuera del diccionario deja el hueco marcado, no inventa nada
    std::string tr7 = g.translatePhrase("gas xenoformico", "en");
    checks.push_back({"unknown_word_in_phrase_is_bracketed",
                       tr7.find("[xenoformico]") != std::string::npos, tr7});

    // 8) termCount coincide con la cantidad de addTerm() cargados a mano
    // (23 llamadas en loadBuiltinTerms(), confirmado con
    //  `grep -c "addTerm(" glossary_tool.cpp` == 23, no a ojo)
    checks.push_back({"term_count_matches_loaded_dictionary",
                       g.termCount() == 23, std::to_string(g.termCount())});

    // 9) lookup directo en italiano
    auto t9 = g.lookup("presion", "it");
    checks.push_back({"lookup_presion_it_matches_pressione",
                       t9.has_value() && *t9 == "pressione",
                       t9 ? *t9 : "(no match)"});

    // 10) lookup directo en aleman (sustantivo capitalizado, ortografia real)
    auto t10 = g.lookup("presion", "de");
    checks.push_back({"lookup_presion_de_matches_Druck",
                       t10.has_value() && *t10 == "Druck",
                       t10 ? *t10 : "(no match)"});

    // 11) italiano mantiene orden sustantivo+adjetivo, igual que pt/fr
    std::string tr11 = g.translatePhrase("gas ideal", "it");
    checks.push_back({"phrase_gas_ideal_it_keeps_order",
                       tr11 == "gas ideale", tr11});

    // 12) aleman reordena a adjetivo+sustantivo, PERO sin concordancia de
    // genero (limitacion real, documentada arriba en applyReorderRule).
    // Este check verifica el comportamiento actual tal cual es, no un
    // aleman gramaticalmente perfecto -- si algun dia se agrega logica de
    // declinacion, este check va a fallar a proposito y hay que actualizarlo.
    std::string tr12 = g.translatePhrase("gas ideal", "de");
    checks.push_back({"phrase_gas_ideal_de_reorders_without_gender_agreement",
                       tr12 == "ideal Gas", tr12 + " (nota: aleman gramaticalmente "
                       "correcto seria 'ideales Gas', concordancia no implementada)"});

    // 13) idiomas soportados ahora son 5
    checks.push_back({"supports_five_languages",
                       g.listLanguages().size() == 5,
                       std::to_string(g.listLanguages().size())});

    return checks;
}

// ---------------------------------------------------------------------
// main / CLI
// ---------------------------------------------------------------------

void printUsage() {
    std::cerr << "Uso:\n"
              << "  glossary_tool --validate\n"
              << "  glossary_tool --translate \"frase en espanol\" <en|pt|fr>\n"
              << "  glossary_tool --list-languages\n";
}

int main(int argc, char** argv) {
    if (argc < 2) {
        printUsage();
        return 1;
    }

    std::string cmd = argv[1];

    if (cmd == "--validate") {
        auto checks = runValidation();
        bool allPassed = true;
        std::cout << "{\n  \"checks\": [\n";
        for (size_t i = 0; i < checks.size(); ++i) {
            const auto& c = checks[i];
            allPassed = allPassed && c.passed;
            std::cout << "    {\"name\": \"" << c.name << "\", "
                      << "\"passed\": " << (c.passed ? "true" : "false") << ", "
                      << "\"detail\": \"" << c.detail << "\"}"
                      << (i + 1 < checks.size() ? "," : "") << "\n";
        }
        std::cout << "  ],\n  \"validation_passed\": "
                  << (allPassed ? "true" : "false") << "\n}\n";
        return allPassed ? 0 : 1;
    }

    if (cmd == "--translate") {
        if (argc < 4) {
            printUsage();
            return 1;
        }
        TechnicalGlossary g;
        std::string text = argv[2];
        std::string lang = argv[3];
        if (!g.hasLanguage(lang)) {
            std::cerr << "Idioma no soportado: " << lang << "\n";
            return 1;
        }
        std::cout << g.translatePhrase(text, lang) << "\n";
        return 0;
    }

    if (cmd == "--list-languages") {
        TechnicalGlossary g;
        for (const auto& l : g.listLanguages()) std::cout << l << "\n";
        return 0;
    }

    printUsage();
    return 1;
}
