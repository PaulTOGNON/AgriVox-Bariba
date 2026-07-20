// Configuration globale
let mockMode = true;
let currentCrop = "coton";
let currentTreatment = "pesticide";

// Questions et types associés
const queriesInfo = {
    "Nna nɛɛra gbi kpunu tɔcotoni mɛ ?": {
        key: "chenilles",
        crop: "coton",
        treatment: "pesticide"
    },
    "Maasi nɛɛra doke yàkuru mɛ ?": {
        key: "maas",
        crop: "maïs",
        treatment: "engrais"
    },
    "Tɔcotoni doke yoko mɛ ?": {
        key: "yoko",
        crop: "coton",
        treatment: "engrais"
    }
};

// Initialisation de la page
document.addEventListener("DOMContentLoaded", () => {
    // Vérifier l'état initial de la case de simulation
    const mockToggle = document.getElementById("mockModeToggle");
    mockMode = mockToggle.checked;
    updateStatusBadge();
});

function toggleMockMode() {
    const mockToggle = document.getElementById("mockModeToggle");
    mockMode = mockToggle.checked;
    updateStatusBadge();
    
    // Si on change de mode, on réinitialise l'affichage pour éviter les incohérences
    resetPipeline();
}

function updateStatusBadge() {
    const badge = document.getElementById("apiStatusBadge");
    const label = document.getElementById("statusLabel");
    const dot = badge.querySelector(".status-dot");
    
    if (mockMode) {
        label.innerText = "Mode Simulation Actif";
        dot.className = "status-dot green";
        badge.style.background = "rgba(16, 185, 129, 0.05)";
        badge.style.borderColor = "rgba(16, 185, 129, 0.2)";
    } else {
        label.innerText = "Mode API OpenAI Connecté";
        dot.className = "status-dot blue";
        badge.style.background = "rgba(0, 188, 212, 0.05)";
        badge.style.borderColor = "rgba(0, 188, 212, 0.2)";
    }
}

// Sélection d'une question type
function selectQuery(text, key) {
    document.getElementById("textInput").value = text;
    
    // Mettre en valeur le bouton sélectionné
    const buttons = document.querySelectorAll(".query-btn");
    buttons.forEach(btn => {
        if (btn.innerText.includes(text.substring(0, 10))) {
            btn.classList.add("selected");
        } else {
            btn.classList.remove("selected");
        }
    });
    
    resetPipeline();
}

// Simulation d'enregistrement vocal
let isRecording = false;
function toggleRecording() {
    const micBtn = document.getElementById("micBtn");
    const instruction = document.getElementById("voiceInstruction");
    const textInput = document.getElementById("textInput");
    
    if (isRecording) {
        return; // Éviter les double-clics
    }
    
    isRecording = true;
    micBtn.classList.add("recording");
    instruction.innerText = "🎙️ Enregistrement de votre voix en Baatonum... Parlez maintenant.";
    
    // Sélectionner une question au hasard si le champ est vide
    if (!textInput.value) {
        textInput.value = "Nna nɛɛra gbi kpunu tɔcotoni mɛ ?";
    }
    
    setTimeout(() => {
        micBtn.classList.remove("recording");
        instruction.innerText = "✅ Enregistrement terminé. Traitement du signal audio...";
        isRecording = false;
        
        // Lancer automatiquement l'analyse
        processQuery();
    }, 2500); // Enregistrement de 2.5 secondes
}

// Réinitialisation du pipeline visuel
function resetPipeline() {
    document.querySelectorAll(".step-card").forEach(card => {
        card.classList.remove("active");
    });
    document.getElementById("pipelineAsrText").innerText = "-";
    document.getElementById("pipelineTranslation").innerText = "-";
    document.getElementById("pipelineDiagnosis").innerHTML = "-";
    document.getElementById("glossaryTags").innerHTML = '<span class="glossary-placeholder">Aucun mot analysé</span>';
    
    document.getElementById("toolNotNeededText").style.display = "block";
    document.getElementById("toolContent").style.display = "none";
    document.getElementById("toolResult").innerText = "En attente de calcul...";
}

// Flux d'analyse principal
async function processQuery() {
    const textInput = document.getElementById("textInput").value.trim();
    if (!textInput) {
        alert("Veuillez saisir ou enregistrer une question en Baatonum.");
        return;
    }
    
    resetPipeline();
    const btnSubmit = document.getElementById("btnSubmit");
    btnSubmit.disabled = true;
    btnSubmit.innerText = "Analyse...";
    
    try {
        // --- ÉTAPE 1 : TRADUCTION ---
        const transResponse = await fetch("/api/translate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text: textInput })
        });
        
        if (!transResponse.ok) throw new Error("Erreur de traduction backend");
        const transData = await transResponse.json();
        
        // Activer étape 1
        const step1 = document.getElementById("step1");
        step1.classList.add("active");
        document.getElementById("pipelineAsrText").innerText = textInput;
        
        // Remplir le glossaire
        const glossaryContainer = document.getElementById("glossaryTags");
        if (transData.glossary_used && transData.glossary_used.length > 0) {
            glossaryContainer.innerHTML = "";
            transData.glossary_used.forEach(item => {
                const tag = document.createElement("span");
                tag.className = "glossary-tag";
                tag.innerHTML = `<i data-lucide="book" class="glossary-icon"></i> <strong>${item.mot}</strong> = ${item.definition.split(' ')[0]}`;
                tag.title = `${item.mot} : ${item.definition}`;
                glossaryContainer.appendChild(tag);
            });
            // Rendre les nouvelles icônes dynamiques
            lucide.createIcons();
        } else {
            glossaryContainer.innerHTML = '<span class="glossary-placeholder">Aucune correspondance dans le glossaire local</span>';
        }
        
        // Pause esthétique pour visualiser l'enchaînement
        await sleep(1200);
        
        // --- ÉTAPE 2 : DIAGNOSTIC ---
        const diagResponse = await fetch("/api/diagnose", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ translated_text: transData.translated_text })
        });
        
        if (!diagResponse.ok) throw new Error("Erreur de diagnostic backend");
        const diagData = await diagResponse.json();
        
        // Activer étape 2
        const step2 = document.getElementById("step2");
        step2.classList.add("active");
        document.getElementById("pipelineTranslation").innerText = transData.translated_text;
        
        // Affichage formatté du diagnostic (convertit le Markdown basique en HTML)
        let formattedDiag = diagData.diagnosis
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>');
        document.getElementById("pipelineDiagnosis").innerHTML = formattedDiag;
        
        currentCrop = diagData.crop || "coton";
        
        // Détecter le type de traitement (engrais ou pesticide)
        const lowerText = transData.translated_text.lowerCase || transData.translated_text.toLowerCase();
        if (lowerText.includes("engrais") || lowerText.includes("fertiliser") || lowerText.includes("fertilisant")) {
            currentTreatment = "engrais";
        } else {
            currentTreatment = "pesticide";
        }
        
        await sleep(1200);
        
        // --- ÉTAPE 3 : OUTIL DE CALCUL (TOOL CALLING) ---
        const step3 = document.getElementById("step3");
        if (diagData.needs_calculation) {
            step3.classList.add("active");
            document.getElementById("toolNotNeededText").style.display = "none";
            document.getElementById("toolContent").style.display = "flex";
            
            // Pré-remplir le formulaire d'outil
            document.getElementById("calcTreatment").value = currentTreatment;
            
            // Lancer le calcul initial
            await runToolCall();
        } else {
            document.getElementById("toolNotNeededText").style.display = "block";
            document.getElementById("toolContent").style.display = "none";
        }
        
        await sleep(1000);
        
        // --- ÉTAPE 4 : SYNTHÈSE VOCALE (TTS) ---
        const step4 = document.getElementById("step4");
        step4.classList.add("active");
        
        // Activer la synthèse vocale réelle du navigateur (Gratuit et hors-ligne)
        if ('speechSynthesis' in window) {
            window.speechSynthesis.cancel(); // Stopper toute lecture en cours
            const speechText = `La traduction en français est : "${transData.translated_text}". Le diagnostic recommande : ${currentCrop === 'coton' ? "un traitement contre les chenilles de la capsule." : "la fertilisation du maïs."} Le calcul de dosage sécurisé a été mis à jour.`;
            const utterance = new SpeechSynthesisUtterance(speechText);
            utterance.lang = 'fr-FR';
            utterance.rate = 1.0;
            window.speechSynthesis.speak(utterance);
        }
        
    } catch (error) {
        console.error(error);
        alert("Une erreur s'est produite lors de la communication avec le serveur.");
    } finally {
        btnSubmit.disabled = false;
        btnSubmit.innerText = "Analyser";
    }
}

// Lancement du calcul de dosage (Programmatic Tool Call)
async function runToolCall() {
    const surface = parseFloat(document.getElementById("calcSurface").value) || 1.0;
    const unit = document.getElementById("calcUnit").value;
    const treatment = document.getElementById("calcTreatment").value;
    
    const resultBox = document.getElementById("toolResult");
    resultBox.innerText = "Calcul sécurisé en cours par GPT-5.6 Sol...";
    
    try {
        const response = await fetch("/api/calculate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                crop: currentCrop,
                treatment_type: treatment,
                surface: surface,
                unit: unit
            })
        });
        
        if (!response.ok) throw new Error("Erreur de calcul backend");
        const data = await response.json();
        
        resultBox.innerHTML = `
            <strong>Résultat du bac à sable (calculate_dosage) :</strong><br>
            🎯 Surface convertie : ${data.surface_hectares} ha<br>
            📦 Quantité requise : <strong>${data.product_needed}</strong><br>
            💧 Dilution nécessaire : ${data.dilution_water}<br><br>
            <em>Instructions d'application :</em><br>
            ${data.instructions.replace(/\n/g, '<br>')}
        `;
    } catch (error) {
        resultBox.innerText = "Erreur lors du calcul.";
    }
}

// Fonction utilitaire de pause
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}
