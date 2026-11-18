# HWPX 편집 연산

| 연산 | 필요한 JSON 키 | 선택 키·의미 |
|---|---|---|
| `text.range` | `target,start,end,value` | 삽입은 start=end, 삭제는 value="" |
| `text.replace` | `text,with` | `target,all_matches` |
| `paragraph.insert-before/insert-after` | `target` | `text` |
| `paragraph.delete/split/merge-next` | `target` | split은 `offset` |
| `format.text` | `target,properties` | `start,end`; 속성 `font,size,color,bold,italic,underline` |
| `format.paragraph` | `target,properties` | `align,left,right,indent,before,after,line-spacing,page-break,column-break` |
| `format.numbering` | `target` | `kind:number/bullet/none`, `ident,level,start,character,pattern`; 반환 ID를 다음 문단에 재사용 |
| `section.set` | `index,properties` | `width,height,landscape,left,right,top,bottom,header,footer,gutter,columns,column-gap` |
| `table.create` | `target,rows,cols` | `values,width,row_height` |
| `table.insert-row/insert-column` | `target,index` | `size` |
| `table.delete-row/delete-column` | `target,index` | 대상 트랙의 셀 내용 삭제는 의도한 삭제로 처리 |
| `table.merge` | `target,row,column,end_row,end_column` | 끝 행/열은 포함, 내용은 행 우선 순서로 유지 |
| `table.split-cell` | `target,row,column` | 기본은 병합 해제. 비병합 셀은 `rows,columns`로 세분화 |
| `table.transpose/delete` | `target` | 전체 표 전치/삭제 |
| `table.split-table` | `target,index` | 행 경계에서 분리; 반환 target이 두 번째 표 |
| `table.merge-table` | `target,other` | 열 트랙이 같은 두 표 합치기 |
| `table.resize` | `target` | `width,height`; 전체 트랙을 균등 재분배 |
| `table.border` | `target,properties` | `color,width,type`; 현재 모든 셀의 네 변 적용 |
| `table.calculate` | `target,formula` | `row,column,write`; 결과 기록 시 첫 문단에 씀 |
| `image.insert/replace` | `target,path` | insert target은 문단, replace는 그림; `properties` |
| `image.set/delete` | `target` | 속성은 `width,height,rotation,inline,x,y,brightness,contrast,crop-left/right/top/bottom` |
| `control.create` | `target,kind` | `text,name,properties`; kind는 header/footer/footNote/endNote/bookmark/field/equation |
| `control.set/rename/delete` | `target` | `text,name,properties`; 일반 내부 내용은 inspect의 문단 주소로 편집 |
| `style.list/create/rename/update/apply/delete` | 동작별 선택 | `ident,name,target,replacement,properties`; create는 원본 스타일 ident 필요 |
| `clipboard.copy` | `target,destination` | 같은 문서 내 문단/개체 복제, 시스템 클립보드를 사용하지 않음 |
| `clipboard.html` | `target,markup` | 단순 문단·굵게·기울임·밑줄·줄바꿈, 미지원 태그/속성은 거부 |
| `shape.create` | `target` | 현재 사각형만 지원; `width,height,text,fill,stroke` |
| `shape.set/delete` | `target` | `properties:x,y,z,fill,stroke,inline,locked` |

길이는 별도 표시가 없으면 mm, 글자 크기는 pt, 줄간격은 %, 색은 `#RRGGBB`입니다. 그림 자르기는 `imgDim`의 원본 좌표 단위입니다. 새 그림은 이를 원본 픽셀 좌표로 통일합니다. 기존 파일의 좌표계를 임의로 재정의하지 않습니다.

수식 개체 생성은 `text`에 한글 수식 스크립트(예: `a over b`)를 넣습니다. `properties`는 `size,color,width,height`입니다. 현재 크기 자동 측정은 미구현이므로 정확한 표시 크기는 직접 지정해야 합니다. 표 계산식은 별개이며 `SUM`, `AVG/AVERAGE`, `PRODUCT`, `MIN/MAX`, `COUNT`, 산술·삼각·반올림 함수, `IF`, 셀/범위·방향·와일드카드 참조를 지원합니다. 셀의 첫 문단 숫자만 읽고 계산 결과를 한 번 기록하며, 다른 계산식의 재귀 평가와 자동 재계산은 지원하지 않습니다. 한컴과의 전체 의미 일치는 보장하지 않습니다.

## 배치 예시

```json
[
  {"op":"text.range","target":"Contents/section0.xml#0","start":0,"end":0,"value":"문서 제목\n본문"},
  {"op":"format.text","target":"Contents/section0.xml#0","start":0,"end":5,"properties":{"size":20,"bold":true,"color":"#2463A6"}},
  {"op":"paragraph.insert-after","target":"Contents/section0.xml#0","text":""},
  {"op":"table.create","target":"Contents/section0.xml#1","rows":2,"cols":3,"values":[["항목","수량","금액"],["예시","2","1000"]],"width":160,"row_height":10}
]
```
