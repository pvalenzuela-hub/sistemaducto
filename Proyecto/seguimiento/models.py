from django.db import models
from django.contrib.auth.models import User

# Create your models here.
class Estadocotizacion(models.Model):
    nombre = models.CharField(max_length=50, null=True, blank=True)

    class Meta:
        db_table = 'Estadocotizacion'


class Estadofactura(models.Model):
    nombre = models.CharField(max_length=50, null=True, blank=True)

    class Meta:
        db_table = 'Estadofactura'

class T_Categoria(models.Model):
    IdCategoria = models.AutoField(primary_key=True)
    NombreCat = models.CharField(max_length=100)

    def __str__(self):
        return self.NombreCat

    class Meta:
        managed = False
        ordering = ["NombreCat"]
        verbose_name = 'Categoría'
        verbose_name_plural = 'Categorías'
        db_table = 'T_Categoria'
        
class TipoEntrega(models.Model):
    idtipoentrega = models.AutoField(db_column='IdTipoEntrega', primary_key=True)
    descripcion = models.CharField(db_column='Descripcion', max_length=100, null=True, blank=True)
    color = models.CharField(db_column='Color', max_length=50, null=True, blank=True)
    factorTiempo = models.FloatField(db_column='FactorTiempo')

    class Meta:
        managed = False
        db_table = '[ducto].[T_TipoEntrega]'
        
from django.db import models

class Testadocliente(models.Model):
    idestadocliente = models.AutoField(db_column='IdEstadoCliente', primary_key=True)
    descrip = models.CharField(db_column='Descrip', max_length=100, null=True, blank=True)
    
    class Meta:
        managed = False
        db_table = 'T_EstadoCliente'
        
class Tcomppago(models.Model):
    idcomppago = models.AutoField(db_column='IdCompPago', primary_key=True)
    descrip = models.CharField(db_column='Descrip', max_length=100, null=True, blank=True)
    
    class Meta:
        managed = False
        db_table = 'T_CompPago'


class TFpago(models.Model):
    idfpago = models.AutoField(db_column='IdFpago', primary_key=True)
    codfp = models.IntegerField(db_column='CodFP', null=True, blank=True)
    concepto = models.CharField(db_column='Concepto', max_length=255)
    regionrm = models.IntegerField(db_column='RegionRM', null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'tFpago'
        ordering = ['codfp']

    def __str__(self):
        return self.concepto


class AspNetUser(models.Model):
    id = models.CharField(db_column='Id', primary_key=True, max_length=128)
    nombrecompleto = models.TextField(db_column='NombreCompleto', null=True, blank=True)
    email = models.CharField(db_column='Email', max_length=256, null=True, blank=True)
    username = models.CharField(db_column='UserName', max_length=256, null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'AspNetUsers'

    def __str__(self):
        return (self.nombrecompleto or self.username or self.email or self.id).strip()

class Cliente(models.Model):
    idcliente = models.AutoField(db_column='IdCliente', primary_key=True)
    rut = models.DecimalField(db_column='Rut', max_digits=10, decimal_places=0, null=True, blank=True)
    dvrut = models.CharField(db_column='DVrut', max_length=1, null=True, blank=True)
    razonsocial = models.CharField(db_column='RazonSocial', max_length=80, null=True, blank=True)
    direccion = models.CharField(db_column='Direccion', max_length=200, null=True, blank=True)
    telefono = models.CharField(db_column='Telefono', max_length=200, null=True, blank=True)
    horariollamada = models.CharField(db_column='HorarioLlamada', max_length=200, null=True, blank=True)
    direcfactura = models.CharField(db_column='DirecFactura', max_length=200, null=True, blank=True)
    horariorecep = models.CharField(db_column='HorarioRecep', max_length=200, null=True, blank=True)
    direcretiroch = models.CharField(db_column='DirecRetiroCH', max_length=200, null=True, blank=True)
    horarioretiroch = models.CharField(db_column='HorarioRetiroCH', max_length=200, null=True, blank=True)
    comentario = models.TextField(db_column='Comentario', null=True, blank=True)
    estado = models.CharField(db_column='Estado', max_length=1, null=True, blank=True)
    esprincipal = models.BooleanField(db_column='EsPrincipal', null=True, blank=True)
    idcliente_p = models.ForeignKey(
    'self',
    db_column='IdCliente_P',
    on_delete=models.DO_NOTHING,
    null=True,
    blank=True
)
    idestadocliente = models.ForeignKey(Testadocliente, db_column='IdEstadoCliente', on_delete=models.DO_NOTHING)
    idcomppago = models.ForeignKey(Tcomppago, db_column='IdCompPago', on_delete=models.DO_NOTHING)
    insercion = models.DateTimeField(db_column='Insercion', null=False)

    class Meta:
        managed = False
        db_table = 'Cliente'

    def __str__(self):
        return self.razonsocial or f"Cliente {self.idcliente}"
    
class ClienteCategoria(models.Model):
    idclientecat = models.AutoField(db_column='IdClienteCAT', primary_key=True)
    idcliente = models.ForeignKey(Cliente, db_column='IdCliente', on_delete=models.DO_NOTHING)
    idcategoria = models.ForeignKey(T_Categoria, db_column='IdCategoria', on_delete=models.DO_NOTHING)
    
    class Meta:
        managed = False
        db_table = 'Cliente_Categoria'


class ClienteSeg(models.Model):
    idsegcliente = models.AutoField(db_column='IdSegCliente', primary_key=True)
    idcliente = models.ForeignKey(
        Cliente,
        db_column='IdCliente',
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        related_name='seguimientos'
    )
    fecha = models.DateTimeField(db_column='Fecha', null=True, blank=True)
    iduser = models.CharField(db_column='IdUser', max_length=128, null=True, blank=True)
    nota = models.CharField(db_column='Nota', max_length=300, null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'Cliente_Seg'
        ordering = ['-fecha', '-idsegcliente']

    def __str__(self):
        return f"Seguimiento cliente {self.idcliente_id}"


class ClienteAgenda(models.Model):
    id = models.AutoField(db_column='Id', primary_key=True)
    idcliente = models.ForeignKey(
        Cliente,
        db_column='IdCliente',
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        related_name='agenda_clientes'
    )
    fecha = models.DateTimeField(db_column='Fecha', null=True, blank=True)
    titulo = models.CharField(db_column='Titulo', max_length=100, null=True, blank=True)
    descrip = models.CharField(db_column='Descrip', max_length=200, null=True, blank=True)
    estado = models.IntegerField(db_column='Estado', null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'Cliente_Agenda'
        ordering = ['-fecha', '-id']

    def __str__(self):
        return self.titulo or (self.idcliente.razonsocial if self.idcliente else f"Agenda {self.id}")
          
class Clientecontacto(models.Model):
    idcontacto = models.AutoField(db_column='IdContacto', primary_key=True)
    idcliente = models.ForeignKey(Cliente,db_column='IdCliente', on_delete=models.DO_NOTHING)
    tipocontacto = models.CharField(db_column='TipoContacto', max_length=1, null=False, blank=False)
    nombrecontacto = models.CharField(db_column='NombreContacto', max_length=80, null=True, blank=True)
    cargo = models.CharField(db_column='Cargo', max_length=80, null=True, blank=True)
    telefono = models.CharField(db_column='Telefono', max_length=50, null=True, blank=True)
    email = models.CharField(db_column='eMail', max_length=80, null=True, blank=True)
    fecharegistro = models.DateTimeField(db_column='FechaRegistro')
    
    class Meta:
        managed = False
        db_table = 'Cliente_Contacto'

    def __str__(self):
        return self.nombrecontacto or f"Contacto {self.idcontacto}"
        

class Cotizacion(models.Model):
    idcotizacion = models.AutoField(db_column='IdCotizacion', primary_key=True)
    numcotizacion = models.DecimalField(
        db_column='NumCotizacion',
        max_digits=10,
        decimal_places=0,
        null=True,
        blank=True
    )
    numcorr = models.IntegerField(db_column='NumCorr', null=True, blank=True)
    fecha = models.DateField(db_column='Fecha', null=True, blank=True)

    idcliente = models.ForeignKey(
        Cliente,
        db_column='IdCliente',
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True
    )

    idcontacto = models.ForeignKey(
        Clientecontacto,
        db_column='IdContacto',
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True
    )

    nombreproyecto = models.CharField(db_column='NombreProyecto', max_length=100, null=True, blank=True)
    dirproyecto = models.CharField(db_column='DirProyecto', max_length=80, null=True, blank=True)
    codregion = models.IntegerField(db_column='CodRegion', null=True, blank=True)
    destino = models.CharField(db_column='Destino', max_length=80, null=True, blank=True)
    pisos = models.CharField(db_column='Pisos', max_length=50, null=True, blank=True)
    edificios = models.IntegerField(db_column='Edificios', null=True, blank=True)
    valortotal = models.FloatField(db_column='ValorTotal', null=True, blank=True)
    moneda = models.CharField(db_column='Moneda', max_length=2, null=True, blank=True)
    estado = models.IntegerField(db_column='Estado', null=True, blank=True)
    idusuario = models.CharField(db_column='IdUsuario', max_length=15, null=True, blank=True)
    fechaact = models.DateTimeField(db_column='FechaACT', null=True, blank=True)
    esactiva = models.BooleanField(db_column='EsActiva', null=True, blank=True)
    fechaaceptacion = models.DateField(db_column='FechaAceptacion', null=True, blank=True)
    mt2 = models.IntegerField(db_column='Mt2', null=True, blank=True)
    fecharegistro = models.DateTimeField(db_column='FechaRegistro', null=True, blank=True)
    estadocotizacion = models.ForeignKey(Estadocotizacion,db_column='estadocotizacion_id',on_delete=models.DO_NOTHING, null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'Cotizacion'

    def __str__(self):
        return f"Cotización {self.numcotizacion or self.idcotizacion}"


class DestinoCotizacion(models.Model):
    iddestino = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=50)

    class Meta:
        managed = False
        db_table = 'DestinoCotizacion'
        ordering = ['iddestino']

    def __str__(self):
        return self.nombre


class MonedaCotizacion(models.Model):
    idmoneda = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=10)

    class Meta:
        managed = False
        db_table = 'MonedaCotizacion'
        ordering = ['idmoneda']

    def __str__(self):
        return self.nombre


class ItemCotizacion(models.Model):
    iditem = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=255)

    class Meta:
        managed = False
        db_table = 'ItemCotizacion'
        ordering = ['iditem']

    def __str__(self):
        return self.nombre


class NotaCotizacion(models.Model):
    idnota = models.AutoField(primary_key=True)
    nota = models.TextField()

    class Meta:
        managed = False
        db_table = 'tNotas'
        ordering = ['idnota']

    def __str__(self):
        return self.nota


class CotizacionValor(models.Model):
    idcotizacionvalor = models.AutoField(primary_key=True)
    idcotizacion = models.ForeignKey(Cotizacion, db_column='IdCotizacion', on_delete=models.DO_NOTHING)
    item = models.IntegerField(db_column='Item')
    glosa = models.CharField(db_column='Glosa', max_length=255)
    valor = models.DecimalField(db_column='Valor', max_digits=18, decimal_places=2, null=True, blank=True)
    opcional = models.CharField(db_column='Opcional', max_length=1, null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'Cotizacion_Valor'
        ordering = ['item']

    def __str__(self):
        return f"{self.idcotizacion_id} - {self.glosa}"


class CotizacionNota(models.Model):
    idcotizacionnota = models.AutoField(primary_key=True)
    idcotizacion = models.ForeignKey(Cotizacion, db_column='IdCotizacion', on_delete=models.DO_NOTHING)
    idnota = models.ForeignKey(NotaCotizacion, db_column='IdNota', on_delete=models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'Cotizacion_Notas'
        ordering = ['idcotizacionnota']

    def __str__(self):
        return f"{self.idcotizacion_id} - {self.idnota_id}"


class CotizacionFpago(models.Model):
    idcotizacionfpago = models.AutoField(primary_key=True)
    idcotizacion = models.ForeignKey(Cotizacion, db_column='IdCotizacion', on_delete=models.DO_NOTHING)
    linea = models.IntegerField(db_column='Linea')
    concepto = models.TextField(db_column='Concepto')

    class Meta:
        managed = False
        db_table = 'Cotizacion_FPago'
        ordering = ['linea']

    def __str__(self):
        return f"{self.idcotizacion_id} - {self.linea}"
    
class Tregion(models.Model):
    codregion = models.IntegerField(db_column='CodRegion', primary_key=True)
    descrip = models.CharField(db_column='Descrip', max_length=50, null=True, blank=True)
    valor = models.IntegerField(db_column='Valor', null=True)
    orden = models.IntegerField(db_column='Orden', null=True)
    
    class Meta:
        managed = False
        db_table = 'tRegion'

    def __str__(self):
        return self.descrip or str(self.codregion)
        
class estadoproyecto(models.Model):
    id = models.AutoField(primary_key=True, null=False)
    nombre = models.CharField(max_length=100, null=False, blank=False)
    color = models.CharField(max_length=80, null=True, blank=True)
    forcolor = models.CharField(max_length=80, null=True, blank=True)
    
    class Meta:
        db_table = 'Estadoproyecto'
        
class TDuracionProyecto(models.Model):
    idtamano = models.AutoField(db_column='IdTamano', primary_key=True)
    descripcion = models.CharField(db_column='Descripcion', max_length=100, null=True, blank=True)
    duracionhoras = models.FloatField(db_column='DuracionHoras', null=True, blank=True)

    class Meta:
        managed = False
        db_table = '[ducto].[T_DuracionProyecto]'

    def __str__(self):
        return self.descripcion or f"Duración {self.idtamano}"
    
class Proyecto(models.Model):
    idproyecto = models.DecimalField(
        db_column='IdProyecto',
        primary_key=True,
        max_digits=10,
        decimal_places=0
    )

    fechacreacion = models.DateField(db_column='FechaCreacion', null=True, blank=True)

    idcotizacion = models.ForeignKey(
        Cotizacion,
        db_column='IdCotizacion',
        on_delete=models.DO_NOTHING,
        null=False,
        blank=False
    )

    fpago = models.CharField(db_column='FPago', max_length=250, null=True, blank=True)
    valor = models.FloatField(db_column='Valor', null=True, blank=True)
    estado = models.IntegerField(db_column='Estado', null=True, blank=True)

    numconf = models.CharField(db_column='NumCONF', max_length=50, null=True, blank=True)
    medioconf = models.CharField(db_column='MedioCONF', max_length=80, null=True, blank=True)
    fechaconf = models.DateField(db_column='FechaCONF', null=True, blank=True)

    idcliente = models.ForeignKey(
        Cliente,
        db_column='IdCliente',
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        related_name='proyectos_principales'
    )

    fechaprimereenvio = models.DateField(db_column='FechaPrimerEnvio', null=True, blank=True)
    fechaact = models.DateField(db_column='FechaACT', null=True, blank=True)

    quienadjudica = models.CharField(db_column='QuienAdjudica', max_length=80, null=True, blank=True)
    emailadjudicacion = models.CharField(db_column='eMailAdjudicacion', max_length=80, null=True, blank=True)
    fechaadjudicacion = models.DateField(db_column='FechaAdjudicacion', null=True, blank=True)

    conhes = models.CharField(db_column='ConHES', max_length=1, null=True, blank=True)
    coneepp = models.CharField(db_column='ConEEPP', max_length=1, null=True, blank=True)
    conotro = models.CharField(db_column='ConOtro', max_length=1, null=True, blank=True)
    fechaheseepp = models.DateField(db_column='FechaHESEEPP', null=True, blank=True)

    moneda = models.CharField(db_column='Moneda', max_length=2, null=True, blank=True)
    fechaingresoseremi = models.DateField(db_column='FechaIngresoSEREMI', null=True, blank=True)
    fechaaprobseremi = models.DateField(db_column='FechaAprobSEREMI', null=True, blank=True)

    idcliente2 = models.ForeignKey(
        Cliente,
        db_column='IdCliente2',
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        related_name='proyectos_secundarios'
    )

    fechaultseg = models.DateField(db_column='FechaUltSeg', null=True, blank=True)

    idtamano = models.ForeignKey(
        TDuracionProyecto,
        db_column='IdTamano',
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        db_constraint=False
    )

    idcontactofacturacion = models.ForeignKey(
        Clientecontacto,
        db_column='IdContactoFacturacion',
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        related_name='proyectos_facturacion'
    )

    emailcontactofacturacion = models.CharField(
        db_column='eMailContactoFacturacion',
        max_length=80,
        null=True,
        blank=True
    )

    fecharegistrocontacto = models.DateTimeField(
        db_column='fecharegistrocontacto',
        null=True,
        blank=True
    )

    emailenviovistobueno = models.DateField(
        db_column='eMailEnvioVistoBueno',
        null=True,
        blank=True
    )

    incobrable = models.BooleanField(db_column='Incobrable', null=True, blank=True)
    seg_ingreso_seremi = models.BooleanField(db_column='Seg_Ingreso_Seremi', null=True, blank=True)

    emailsegingresoseremi = models.DateField(
        db_column='eMailSegIngresoSeremi',
        null=True,
        blank=True
    )

    emailsegentregav00 = models.DateField(
        db_column='eMailSegEntregaV00',
        null=True,
        blank=True
    )

    fecharegistro = models.DateTimeField(db_column='FechaRegistro', null=True, blank=True)

    propietario = models.CharField(db_column='Propietario', max_length=100, null=True, blank=True)
    rutpropietario = models.CharField(db_column='RutPropietario', max_length=13, null=True, blank=True)
    idoperador = models.CharField(db_column='IdOperador', max_length=15, null=True, blank=True)
    transferarancel = models.CharField(db_column='TransferArancel', max_length=50, null=True, blank=True)
    arancel = models.FloatField(db_column='Arancel', null=True, blank=True)
    ntramiteseremi = models.CharField(db_column='NTramiteSeremi', max_length=50, null=True, blank=True)

    fechasolacreditacion = models.DateField(db_column='FechaSolAcreditacion', null=True, blank=True)
    fechasolingreso = models.DateField(db_column='FechaSolIngreso', null=True, blank=True)
    fechacargaexp = models.DateField(db_column='FechaCargaExp', null=True, blank=True)
    fechapagoarancel = models.DateField(db_column='FechaPagoArancel', null=True, blank=True)
    fechaingresotimbraje = models.DateField(db_column='FechaIngresoTimbraje', null=True, blank=True)
    fechaaprobtimbraje = models.DateField(db_column='FechaAprobTimbraje', null=True, blank=True)

    nombrereplegal = models.CharField(db_column='NombreRepLegal', max_length=80, null=True, blank=True)
    rutreplegal = models.CharField(db_column='RutRepLegal', max_length=13, null=True, blank=True)

    correo_res_1378_enviado = models.BooleanField(
        db_column='correo_res_1378_enviado',
        null=True,
        blank=True
    )
    correo_res_1378_fecha = models.DateTimeField(
        db_column='correo_res_1378_fecha',
        null=True,
        blank=True
    )

    avisomasivo_seremi_enviado = models.BooleanField(
        db_column='avisomasivo_seremi_enviado',
        null=True,
        blank=True
    )
    avisomasivo_seremi_fecha = models.DateTimeField(
        db_column='avisomasivo_seremi_fecha',
        null=True,
        blank=True
    )

    estadoproyecto = models.ForeignKey(
        estadoproyecto,
        db_column='estadoproyecto_id',
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        related_name='proyecto',
        db_constraint=False)
    
    class Meta:
        managed = False
        db_table = 'Proyecto'

    def __str__(self):
        return f"Proyecto {self.idproyecto}"
    
class Estadoentrega(models.Model):
    idestadoentrega = models.AutoField(db_column='IdEstadoEntrega', primary_key=True)
    descrip = models.CharField(db_column='Descrip', max_length=100, null=True, blank=True)
    
    class Meta:
        managed = False
        db_table = '[ducto].[T_EstadosEntrega]'
    
class Urgencia(models.Model):
    idurgencia = models.AutoField(db_column='IdUrgencia', primary_key=True)
    descrip = models.CharField(db_column='Descrip', max_length=50, null=True, blank=True)
    simbolo = models.CharField(db_column='Simbolo', max_length=1, null=True, blank=True)
    
    class Meta:
        managed = False
        db_table = '[ducto].[T_Urgencias]'
        
class Duracionproyecto(models.Model):
    idtamano = models.AutoField(db_column='IdTamano', primary_key=True)
    descripcion = models.CharField(db_column='Descripcion', max_length=50, null=True, blank=True)
    duracionhoras = models.IntegerField(db_column='DuracionHoras', null=True, blank=True)
    
    class Meta:
        managed = False
        db_table = '[ducto].[T_DuracionProyecto]'
        

class tusuario(models.Model):
    idusuario = models.CharField(db_column='IdUsuario',max_length=15, primary_key=True)
    nombreusuario = models.CharField(db_column='NombreUsuario', max_length=80, null=True, blank=True)
    idperfil = models.IntegerField(db_column='IdPerfil', null=True, blank=True)
    usrclave = models.CharField(db_column='usr_clave', max_length=100, null=True, blank=True)
    estado = models.CharField(db_column='Estado', max_length=1, null=True, blank=True)
    operador = models.BooleanField(db_column='Operador', null=True, blank=True)
    username = models.CharField(db_column='UserName',max_length=50, null=True, blank=True)
    
    class Meta:
        managed = False
        db_table = 'tUsuario'
        
    
class EntregaProyecto(models.Model):
    identrega = models.AutoField(db_column='IdEntrega', primary_key=True)

    rutusercreador = models.CharField(db_column='RutUserCreador', max_length=256, null=True, blank=True)
    fechacreacion = models.DateTimeField(db_column='FechaCreacion', null=True, blank=True)
    fechacalendario = models.DateTimeField(db_column='FechaCalendario', null=True, blank=True)

    idproyecto = models.ForeignKey(
        Proyecto,
        db_column='IdProyecto',
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        db_constraint=False,
        related_name='entregas'
    )

    idtipoentrega = models.ForeignKey(
        TipoEntrega,
        db_column='IdTipoEntrega',
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        db_constraint=False
    )

    idurgencia = models.ForeignKey(Urgencia, db_column='IdUrgencia', on_delete=models.DO_NOTHING,
                                   null=True,
                                   blank=True,
                                   db_constraint=False
                                   )

    fechaentrega = models.DateField(db_column='FechaEntrega', null=True, blank=True)
    horaentrega = models.CharField(db_column='HoraEntrega', max_length=50, null=True, blank=True)
    plazoestdesarrollo = models.CharField(db_column='PlazoEstDesarrollo', max_length=50, null=True, blank=True)

    rutuserdesa1 = models.CharField(db_column='RutUserDesa1', max_length=256, null=True, blank=True)
    fechaasigdesa1 = models.DateTimeField(db_column='FechaAsigDesa1', null=True, blank=True)

    rutuserdesa2 = models.CharField(db_column='RutUserDesa2', max_length=256, null=True, blank=True)
    fechaasigdesa2 = models.DateTimeField(db_column='FechaAsigDesa2', null=True, blank=True)

    rutuserrev1 = models.CharField(db_column='RutUserRev1', max_length=256, null=True, blank=True)
    fechaasigrev1 = models.DateTimeField(db_column='FechaAsigRev1', null=True, blank=True)

    rutuserrev2 = models.CharField(db_column='RutUserRev2', max_length=256, null=True, blank=True)
    fechaasigrev2 = models.DateTimeField(db_column='FechaAsigRev2', null=True, blank=True)

    rutuserdesa3 = models.CharField(db_column='RutUserDesa3', max_length=256, null=True, blank=True)
    fechaasigdesa3 = models.DateTimeField(db_column='FechaAsigDesa3', null=True, blank=True)

    rutuserrev3 = models.CharField(db_column='RutUserRev3', max_length=256, null=True, blank=True)
    fechaasigrev3 = models.DateTimeField(db_column='FechaAsigRev3', null=True, blank=True)

    idestadoentrega = models.ForeignKey(Estadoentrega, db_column='IdEstadoEntrega', on_delete=models.DO_NOTHING,
                                        null=True,
                                        blank=True,
                                        db_constraint=False)

    rutuserupdate = models.CharField(db_column='RutUserUpdate', max_length=256, null=True, blank=True)
    fechaupdate = models.DateTimeField(db_column='FechaUpdate', null=True, blank=True)

    rutuseranula = models.CharField(db_column='RutUserAnula', max_length=256, null=True, blank=True)
    fechaanulacion = models.DateTimeField(db_column='FechaAnulacion', null=True, blank=True)

    class Meta:
        managed = False
        db_table = '[ducto].[EntregaProyecto]'

    def __str__(self):
        return f"Entrega {self.identrega}"
    
class Tipoobservacion(models.Model):
    id = models.AutoField(db_column='IdTipoObservacion', primary_key=True)
    nombre = models.CharField(db_column='Descripcion', max_length=100, null=True, blank=True)
    
    class Meta:
        managed = False
        db_table = '[ducto].[T_TipoObservacion]'

class Calificacion(models.Model):
    id = models.AutoField(db_column='IdCalificaciones', primary_key=True)
    nombre = models.CharField(db_column='Descripcion', max_length=100)
    
    class Meta:
        managed = False
        db_table = '[ducto].[T_Calificaciones]'

class Observacion(models.Model):
    id = models.AutoField(db_column='IdObservacion', primary_key=True)
    tipoobservacion = models.ForeignKey(Tipoobservacion, db_column='IdTipoObservacion',
                                        on_delete=models.DO_NOTHING,
                                        null=True,
                                        blank=True,
                                        db_constraint=False)
    nombre = models.CharField(db_column='Descrip', max_length=300, null=True, blank=True)
    calificacion = models.ForeignKey(Calificacion, db_column='IdCalificaciones',
                                     on_delete=models.DO_NOTHING,
                                     null=True,
                                     blank=True,
                                     db_constraint=False)
    
    class Meta:
        managed = False
        db_table = '[ducto].[T_Observaciones]'
    
class Entregaobservacion(models.Model):
    id = models.AutoField(db_column='IdObservEntrega', primary_key=True)
    entrega = models.ForeignKey(EntregaProyecto, db_column='IdEntrega',
                                on_delete=models.DO_NOTHING,
                                null=True,
                                blank=True,
                                db_constraint=False
                                )
    observacion = models.ForeignKey(Observacion, db_column='IdObservacion',
                                    on_delete=models.DO_NOTHING,
                                    null=True,
                                    blank=True,
                                    db_constraint=False)
    fecha = models.DateTimeField(auto_now=True, db_column='Fecha')
    username = models.ForeignKey(User, db_column='UserName', on_delete=models.DO_NOTHING,
                                 null=True,
                                 blank=True,
                                 db_constraint=False)
    estado = models.IntegerField(db_column='Estado', null=True, blank=True)
    
    class Meta:
        managed = False
        db_table = '[ducto].[Entrega_Observacion]'
    
class Tipoevento(models.Model):
    idtipoevento = models.AutoField(db_column='IdTipoEvento', primary_key=True)
    nombre = models.CharField(db_column='Evento', max_length=50, null=True, blank=True)
    
    class Meta:
        managed = False
        db_table = '[ducto].[T_TipoEvento]'
        
class Entregaevento(models.Model):
    identregaevento = models.AutoField(db_column='IdEntregaEvento', primary_key=True)
    entrega = models.ForeignKey(EntregaProyecto, db_column='IdEntrega', on_delete=models.DO_NOTHING,
                                null=True,
                                blank=True,
                                db_constraint=False)
    tipoevento = models.ForeignKey(Tipoevento, db_column='IdTipoEvento', on_delete=models.DO_NOTHING,
                                   null=True,
                                   blank=True)
    rutorigen = models.CharField(db_column='RutOrigen', max_length=12, null=True, blank=True)
    rutdestino = models.CharField(db_column='RutDestino', max_length=12, null=True, blank=True)
    fechahora = models.DateTimeField(auto_now=True)
    
    class Meta:
        managed = False
        db_table = '[ducto].[EntregaEvento]'
