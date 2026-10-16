{{- define "laai.name" -}}legal-agreement-ai{{- end -}}
{{- define "laai.fullname" -}}{{ .Release.Name }}-legal-ai{{- end -}}
{{- define "laai.image" -}}{{ .Values.image.repository }}:{{ .Values.image.tag | default .Chart.AppVersion }}{{- end -}}
{{- define "laai.labels" -}}
app.kubernetes.io/name: {{ include "laai.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Values.image.tag | default .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end -}}
{{- define "laai.selector" -}}
app.kubernetes.io/name: {{ include "laai.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
{{- define "laai.env" -}}
- { name: APP_ENV, value: {{ .Values.app.env | quote }} }
- { name: DEMO_MODE, value: {{ .Values.app.demoMode | quote }} }
- { name: STORE, value: "postgres" }
- { name: SEARCH, value: {{ .Values.app.search | quote }} }
- { name: PROCESSING, value: {{ .Values.app.processing | quote }} }
- { name: DRAFTING_MODE, value: {{ .Values.app.draftingMode | quote }} }
- { name: LLM_BASE_URL, value: {{ .Values.app.llmBaseUrl | quote }} }
- { name: LLM_MODEL, value: {{ .Values.app.llmModel | quote }} }
- { name: RATE_LIMIT_PER_MIN, value: {{ .Values.app.rateLimitPerMin | quote }} }
- { name: EMBED_URL, value: "http://{{ include "laai.fullname" . }}-embed" }
- { name: GIT_SHA, value: {{ .Values.image.tag | default .Chart.AppVersion | quote }} }
- { name: TMPDIR, value: /tmp }
- name: LLM_API_KEY
  valueFrom: { secretKeyRef: { name: {{ .Values.existingSecret }}, key: LLM_API_KEY, optional: true } }
{{- end -}}
