{{- define "unoarena-placeholder-lib.name" -}}
{{- default .Chart.Name .Values.serviceName | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "unoarena-placeholder-lib.labels" -}}
app.kubernetes.io/name: {{ include "unoarena-placeholder-lib.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/part-of: unoarena
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
unoarena.itba/context: {{ .Values.context | quote }}
{{- end -}}

{{- define "unoarena-placeholder-lib.selectorLabels" -}}
app.kubernetes.io/name: {{ include "unoarena-placeholder-lib.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
